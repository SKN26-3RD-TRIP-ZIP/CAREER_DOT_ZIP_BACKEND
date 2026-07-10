import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.db.models import Prefetch
from django.utils import timezone
from django.db import connection, transaction
from django.db.models import F

from .models import (
    AnalysisSession, JdAnalysis, GeneratedQuestion, QuestionFeedback,
    TalentProfileCategory, TalentProfileTrait, JDTalentProfile, JDTalentProfileItem,
)
from apps.input.models import JobDescription, ResumeMaster, CoverLetter
from .serializers import (
    JDListSerializer, ResumeListSerializer, CoverLetterListSerializer,
    ResumeFullCreateSerializer,
    TalentProfileCategorySerializer, JDTalentProfileSerializer,
)
from apps.input.serializers import (
    JobDescriptionCreateSerializer,
    CoverLetterCreateSerializer,
)
from .services import extract_jd_keywords, analyze_resume
from .services.jd_service              import extract_jd_requirements
from .services.match_service           import calculate_match_score
from .services.result_service          import build_match_result
from .services.gap_service             import calculate_gap, build_gap_message
from .services.question_service        import generate_all_questions
from .services.question_output_service import to_db_records
from .services.utils.guardrails        import InputGuardrail, OutputGuardrail
from apps.accounts.services.points     import (
    apply_point_policy, refund_points, InsufficientPointsError,
)

logger = logging.getLogger(__name__)

# 한 분석당 예상 질문 생성 무료 상한 (최초 생성 + 재생성 누적).
# 초과 시 Phase 2의 포인트 차감으로 확장 예정 (현재는 차단).
MAX_QUESTION_GENERATIONS = 3


def _serialize_generated_questions(jd_analysis):
    questions = jd_analysis.questions.values(
        "id",
        "question_type",
        "question_text",
        "answer",
        "order",
    )
    if hasattr(questions, "order_by"):
        questions = questions.order_by("order")
    serialized = []
    for question in questions:
        item = dict(question)
        if item.get("id") is not None:
            item["id"] = str(item["id"])
        serialized.append(item)
    return serialized


def _resolve_future(future, label: str, fallback):
    """
    Future 결과를 안전하게 가져온다.
    실패 시 fallback 값을 반환하고 에러를 로깅한다.
    """
    try:
        return future.result(), None
    except Exception as e:
        logger.error("[Analysis] %s 실패 — fallback 사용: %s", label, e, exc_info=True)
        return fallback, label


def _run_analysis(session_id: int):
    """
    백그라운드 스레드에서 실행되는 전체 분석 파이프라인.

    [최적화 구조]
    Step1: JD 키워드/요건 추출 + 이력서 분석 — 3개 병렬
    Step2: match_score(임베딩+LLM) ↔ RAG+질문생성(LLM) — 병렬
    Step3: gap 계산(순수 로직) ↔ merge(임베딩) — 병렬
    Step4: STAR 답안 생성 — personality/technical/experience 3그룹 병렬
    """
    session = AnalysisSession.objects.get(id=session_id)
    t_total = time.time()
    try:
        # Step 1: JD 키워드 추출 / JD 자격 요건 추출 / 이력서 분석 — 3개 병렬
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=3) as executor:
            f_jd_kw  = executor.submit(extract_jd_keywords,    session.jd_text)
            f_jd_req = executor.submit(extract_jd_requirements, session.jd_text, session.company_name)
            f_resume = executor.submit(analyze_resume, session.resume_text, session.cover_letter_text)

        jd_kw,          err_jd_kw  = _resolve_future(f_jd_kw,  "JD 키워드 추출",   {})
        jd_req,         err_jd_req = _resolve_future(f_jd_req, "JD 자격 요건 추출", {})
        resume_summary, err_resume = _resolve_future(f_resume, "이력서 분석",       {})
        logger.info("[TIMING] step1 병렬(jd_kw+jd_req+resume): %.2fs", time.time() - t0)

        if err_resume:
            raise RuntimeError("이력서 분석 실패로 파이프라인을 중단합니다.")

        failed_steps = [s for s in [err_jd_kw, err_jd_req] if s]
        if failed_steps:
            logger.warning("[Analysis] session=%s — 일부 단계 fallback 적용: %s", session_id, failed_steps)

        inferred_level = resume_summary.get("career_level", session.career_level)
        session.jd_keywords     = {**jd_kw, "requirements": jd_req}
        session.resume_analysis = resume_summary
        session.career_level    = inferred_level
        session.save(update_fields=["jd_keywords", "resume_analysis", "career_level"])

        # Step 2: 매칭 점수 계산
        # (예상 질문/STAR 생성은 분석에서 분리됨 → /analysis/questions/ 에서 온디맨드 생성)
        t0 = time.time()
        match_result_raw = calculate_match_score(
            jd_keywords=jd_kw,
            resume_analysis=resume_summary,
            cover_letter_text=session.cover_letter_text,
            career_level=inferred_level,
            jd_requirements=jd_req,
            job_role=session.job_role,
        )
        match_result = build_match_result(match_result_raw, inferred_level)
        logger.info("[TIMING] step2 매칭 점수: %.2fs", time.time() - t0)

        # Step 3: gap 계산
        t0 = time.time()
        gap_result = calculate_gap(
            jd_keywords=jd_kw,
            jd_requirements=jd_req,
            resume_analysis=resume_summary,
            unmatched_keywords=match_result["unmatched_keywords"],
            trait_details=match_result.get("trait_details"),
        )
        gap_message = build_gap_message(gap_result, inferred_level)
        logger.info("[TIMING] step3 gap: %.2fs", time.time() - t0)

        # Step 4: JdAnalysis 생성
        jd_analysis = JdAnalysis.objects.create(
            user=session.user,
            jd_id=session.jd_id,
            resume_id=session.resume_id,
            cover_letter_id=session.cover_letter_id,
            match_score=match_result["match_score"],
            tech_score=match_result["tech_score"],
            trait_score=match_result["trait_score"],
            matched_keywords=match_result["matched_keywords"],
            unmatched_keywords=match_result["unmatched_keywords"],
            jd_keywords={**jd_kw, "requirements": jd_req},
            resume_analysis={**resume_summary, "gap": gap_result, "gap_message": gap_message},
            strengths=match_result["strengths"],
            weaknesses=match_result["weaknesses"],
            cl_points=match_result["cl_points"],
        )

        # 예상 질문/STAR은 분석과 분리됨 — 결과 화면의 "예상 질문 생성" 버튼이
        # /analysis/questions/ 를 호출할 때 생성·저장된다 (AnalysisQuestionsView).

        # input.JobDescription에 분석 결과 반영
        # 실패 시 기존 방식(자격요건 필드 나열)으로 폴백
        summary_parts = []
        if jd_req.get("job_type"):
            summary_parts.append(jd_req["job_type"])
        if jd_req.get("min_years"):
            summary_parts.append(f"경력 {jd_req['min_years']}년 이상")
        if jd_req.get("education") and jd_req["education"] != "무관":
            summary_parts.append(jd_req["education"])
        if jd_req.get("required_tech"):
            summary_parts.append(", ".join(jd_req["required_tech"][:5]))
        fallback_summary = " | ".join(summary_parts) if summary_parts else session.job_role

        # company_summary는 별도 AI 호출 없이 extract_jd_requirements() 결과를 재사용한다.
        company_summary = jd_req.get("company_summary") or fallback_summary

        JobDescription.objects.filter(id=session.jd_id).update(
            company_summary=company_summary,
            analysis_status="COMPLETED",
        )

        # 세션에 jd_analysis_id 저장 후 완료
        session.jd_analysis_id = jd_analysis.id
        session.status = "ready"
        session.save(update_fields=["jd_analysis_id", "status", "updated_at"])
        logger.info("[TIMING] ✅ 전체 파이프라인 완료: %.2fs", time.time() - t_total)

    except Exception as e:
        session.status = "failed"
        session.save(update_fields=["status", "updated_at"])
        JobDescription.objects.filter(id=session.jd_id).update(analysis_status="FAILED")
        logger.error("Analysis failed for session %s: %s", session_id, e, exc_info=True)
    finally:
        connection.close()


class JDSelectListView(APIView):
    """
    GET /api/v1/analysis/select/jds/
    분석 시작 시 선택 가능한 내 JD 목록 반환.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        jds = JobDescription.objects.filter(user=request.user)
        serializer = JDListSerializer(jds, many=True)
        return Response({'total': jds.count(), 'results': serializer.data})


class ResumeSelectListView(APIView):
    """
    GET /api/v1/analysis/select/resumes/
    분석 시작 시 선택 가능한 내 이력서 목록 반환.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        resumes = ResumeMaster.objects.filter(user=request.user)
        serializer = ResumeListSerializer(resumes, many=True)
        return Response({'total': resumes.count(), 'results': serializer.data})


class CoverLetterSelectListView(APIView):
    """
    GET /api/v1/analysis/select/cover-letters/
    분석 시작 시 선택 가능한 내 자소서 목록 반환.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cover_letters = CoverLetter.objects.filter(user=request.user)
        serializer = CoverLetterListSerializer(cover_letters, many=True)
        return Response({'total': cover_letters.count(), 'results': serializer.data})


class JDCreateView(APIView):
    """
    POST /api/v1/analysis/create/jds/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = JobDescriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        jd = serializer.save(user=request.user)
        return Response({'jd_id': str(jd.id), 'company_name': jd.company_name, 'position': jd.position}, status=status.HTTP_201_CREATED)


class ResumeCreateView(APIView):
    """
    POST /api/v1/analysis/create/resumes/
    body: {
        name, phone, email, address, github_url, original_text,
        careers: [{company_name, position, start_date, end_date, is_current, description}],
        education: [{school_name, major, degree, start_date, end_date, status}],
        skills: ["Python", "Django", ...],
        certificates: [{name, issued_by, issued_at}]
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ResumeFullCreateSerializer(data=request.data, context={'user': request.user})
        serializer.is_valid(raise_exception=True)
        resume = serializer.save()
        return Response({'resume_id': str(resume.id), 'name': resume.name}, status=status.HTTP_201_CREATED)


class CoverLetterCreateView(APIView):
    """
    POST /api/v1/analysis/create/cover-letters/
    body: { title, company_name, jd_id(optional), items: [{question, answer_text, max_length, order_index}] }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CoverLetterCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        cl = serializer.save(user=request.user)
        return Response({'cover_letter_id': str(cl.id), 'title': cl.title}, status=status.HTTP_201_CREATED)


class AnalysisStartView(APIView):
    """
    POST /api/v1/analysis/analyze/
    입력 데이터 저장 후 백그라운드 분석 시작. 즉시 session_id 반환.

    REQUEST:
        {
            "jd_id":             "uuid",
            "resume_id":         "uuid",
            "cover_letter_id":   "uuid",  (선택)
            "job_role":          "백엔드 개발자",
            "company_name":      "커리어닷집",
            "jd_text":           "...",
            "resume_text":       "...",
            "cover_letter_text": "..."
        }

    RESPONSE (201):
        { "session_id": 1, "status": "analyzing" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        jd_id           = request.data.get("jd_id")
        resume_id       = request.data.get("resume_id")
        cover_letter_id = request.data.get("cover_letter_id")
        career_level    = request.data.get("career_level", "entry")

        if not jd_id:
            logger.warning("[AnalysisStart] user=%s — jd_id 누락", request.user.id)
            return Response({"error": "jd_id는 필수입니다."}, status=400)
        if not resume_id:
            logger.warning("[AnalysisStart] user=%s — resume_id 누락", request.user.id)
            return Response({"error": "resume_id는 필수입니다."}, status=400)

        try:
            jd = JobDescription.objects.get(id=jd_id, user=request.user)
        except JobDescription.DoesNotExist:
            logger.warning("[AnalysisStart] user=%s — JD 없음 jd_id=%s", request.user.id, jd_id)
            return Response({"error": "JD를 찾을 수 없습니다."}, status=400)

        try:
            resume = ResumeMaster.objects.get(id=resume_id, user=request.user)
        except ResumeMaster.DoesNotExist:
            logger.warning("[AnalysisStart] user=%s — 이력서 없음 resume_id=%s", request.user.id, resume_id)
            return Response({"error": "이력서를 찾을 수 없습니다."}, status=400)

        cover_letter_text = ""
        if cover_letter_id:
            try:
                cl = CoverLetter.objects.get(id=cover_letter_id, user=request.user)
                cover_letter_text = "\n\n".join(
                    f"{item.question}\n{item.answer_text}"
                    for item in cl.items.all()
                )
            except CoverLetter.DoesNotExist:
                logger.warning("[AnalysisStart] user=%s — 자소서 없음 cover_letter_id=%s (무시하고 진행)", request.user.id, cover_letter_id)

        jd_text = jd.original_text or ""
        logger.info(
            "[AnalysisStart] user=%s jd_id=%s resume_id=%s cover_letter_id=%s "
            "jd_text_len=%d cl_text_len=%d",
            request.user.id, jd_id, resume_id, cover_letter_id,
            len(jd_text), len(cover_letter_text),
        )
        # 규칙 기반 1차 검사만 수행 (LLM 2차 검사는 guardrails.py 내부에서 별도로 비활성화됨)
        guardrail = InputGuardrail()
        guard_result = guardrail.validate(jd=jd_text, cover_letter=cover_letter_text)
        if not guard_result["valid"]:
            logger.warning(
                "[AnalysisStart] 가드레일 차단 user=%s field=%s error=%s jd_text_len=%d",
                request.user.id, guard_result.get("field"), guard_result["error"], len(jd_text),
            )
            return Response(
                {
                    "error_code": "INVALID_INPUT",
                    "field":      guard_result.get("field"),
                    "message":    guard_result["error"],
                },
                status=400,
            )

        # 동일 조합(jd + resume + cover_letter)으로 완료된 세션이 있으면 재사용
        existing_session = (
            AnalysisSession.objects
            .filter(
                user=request.user,
                jd_id=jd_id,
                resume_id=resume_id,
                cover_letter_id=cover_letter_id if cover_letter_id else None,
                status="ready",
            )
            .order_by("-created_at")
            .first()
        )
        if existing_session:
            logger.info(
                "[AnalysisStart] 기존 세션 재사용 user=%s session_id=%s",
                request.user.id, existing_session.id,
            )
            return Response({"session_id": existing_session.id, "status": "ready"}, status=200)

        session = AnalysisSession.objects.create(
            user=request.user,
            jd_id=jd_id,
            resume_id=resume_id,
            cover_letter_id=cover_letter_id,
            job_role=jd.position,
            company_name=jd.company_name,
            jd_text=jd_text,
            resume_text=resume.original_text or "",
            cover_letter_text=cover_letter_text,
            career_level=career_level,
            status="analyzing",
        )

        threading.Thread(
            target=_run_analysis,
            args=(session.id,),
            daemon=False,
        ).start()

        return Response({"session_id": session.id, "status": "analyzing"}, status=201)


class AnalysisStatusView(APIView):
    """
    POST /api/v1/analysis/status/
    프론트가 2~3초마다 폴링. "ready" 또는 "failed" 되면 폴링 중단.

    REQUEST:  { "session_id": 1 }
    RESPONSE: { "status": "analyzing" | "ready" | "failed", "jd_keywords": [] }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        try:
            session = AnalysisSession.objects.get(id=session_id, user=request.user)
        except AnalysisSession.DoesNotExist:
            return Response({"error": "세션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "status":       session.status,
            "jd_keywords":  session.jd_keywords if session.status == "ready" else [],
        })


class AnalysisMatchView(APIView):
    """
    POST /api/v1/analysis/match/
    분석 완료 후 JdAnalysis 전체 결과 + 생성된 질문 목록 반환.
    interview 앱에서 jd_analysis_id로 질문을 가져간다.

    REQUEST:  { "session_id": 1 }
    RESPONSE (200):
        {
            "jd_analysis_id":  "uuid",
            "match_score":     87.5,
            "jd_keywords":     [...],
            "resume_analysis": {...},
            "strengths":       [...],
            "weaknesses":      [...],
            "cl_points":       [...]
            # 예상 질문은 분리됨 — GET/POST /analysis/questions/ 로 조회·생성
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        try:
            session = AnalysisSession.objects.get(id=session_id, user=request.user)
        except AnalysisSession.DoesNotExist:
            return Response({"error": "세션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        if session.status != "ready":
            return Response(
                {"error": "분석이 아직 완료되지 않았습니다.", "status": session.status},
                status=400,
            )

        try:
            jd_analysis = JdAnalysis.objects.get(id=session.jd_analysis_id)
        except JdAnalysis.DoesNotExist:
            return Response({"error": "분석 결과를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        resume_meta = jd_analysis.resume_analysis
        return Response({
            "jd_analysis_id":      str(jd_analysis.id),
            "match_score":         jd_analysis.match_score,
            "tech_score":          jd_analysis.tech_score,
            "trait_score":         jd_analysis.trait_score,
            "matched_keywords":    jd_analysis.matched_keywords,
            "unmatched_keywords":  jd_analysis.unmatched_keywords,
            "jd_keywords":         jd_analysis.jd_keywords,
            "resume_analysis":     resume_meta,
            "gap":                 resume_meta.get("gap", {}),
            "gap_message":         resume_meta.get("gap_message", {}),
            "strengths":           jd_analysis.strengths,
            "weaknesses":          jd_analysis.weaknesses,
            "cl_points":           jd_analysis.cl_points,
        })


class AnalysisQuestionsView(APIView):
    """
    예상 면접 질문 + STAR 답변 (분석과 분리된 온디맨드 생성).

    GET  /api/v1/analysis/questions/?session_id=1
        → 이미 생성된 질문 반환. 없으면 생성하지 않고 generated=false.
    POST /api/v1/analysis/questions/  { "session_id": 1 }
        → 생성(이미 있으면 기존 반환) 후 질문 목록 반환. 멱등.

    RESPONSE (200):
        {
            "generated": true,
            "questions": [
                {"id": "uuid", "question_type": "technical", "question_text": "...",
                 "answer": {...}, "order": 0},
                ...
            ]
        }
    """
    permission_classes = [IsAuthenticated]

    def _serialize(self, jd_analysis):
        return _serialize_generated_questions(jd_analysis)

    def _ready_analysis(self, request, session_id):
        """(jd_analysis | None, session). 세션 없으면 DoesNotExist 전파."""
        session = AnalysisSession.objects.get(id=session_id, user=request.user)
        if session.status != "ready" or not session.jd_analysis_id:
            return None, session
        return JdAnalysis.objects.get(id=session.jd_analysis_id), session

    def _payload(self, jd_analysis, questions):
        return {
            "generated":         bool(questions),
            "questions":         questions,
            "generation_count":  jd_analysis.generation_count,
            "max_generations":   MAX_QUESTION_GENERATIONS,
        }

    def get(self, request):
        session_id = request.query_params.get("session_id")
        try:
            jd_analysis, _ = self._ready_analysis(request, session_id)
        except AnalysisSession.DoesNotExist:
            return Response({"error": "세션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        if jd_analysis is None:
            return Response({"generated": False, "questions": [], "generation_count": 0,
                             "max_generations": MAX_QUESTION_GENERATIONS})
        return Response(self._payload(jd_analysis, self._serialize(jd_analysis)))

    def post(self, request):
        session_id = request.data.get("session_id")
        regenerate = bool(request.data.get("regenerate"))
        try:
            jd_analysis, session = self._ready_analysis(request, session_id)
        except AnalysisSession.DoesNotExist:
            return Response({"error": "세션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        if jd_analysis is None:
            return Response({"error": "분석이 아직 완료되지 않았습니다."}, status=400)

        existing = self._serialize(jd_analysis)

        # 멱등 조회: 이미 있고 재생성 요청이 아니면 그대로 반환 (카운트 변동 없음)
        if existing and not regenerate:
            return Response(self._payload(jd_analysis, existing))

        # 생성 또는 재생성 — 무료 상한 초과 시 포인트 차감으로 진행
        point_charge = None
        point_idempotency_key = None
        if jd_analysis.generation_count >= MAX_QUESTION_GENERATIONS:
            point_idempotency_key = (
                f"ANALYSIS.EXTRA_QUESTION_GEN:{request.user.id}:"
                f"{jd_analysis.id}:{jd_analysis.generation_count}"
            )
            try:
                point_charge = apply_point_policy(
                    user=request.user,
                    reason_code="ANALYSIS.EXTRA_QUESTION_GEN",
                    reference_id=str(jd_analysis.id),
                    idempotency_key=point_idempotency_key,
                    description="예상 질문 추가 생성 (무료 횟수 소진 후)",
                )
            except InsufficientPointsError:
                return Response(
                    {
                        "error": "무료 생성 횟수를 모두 사용했습니다. 포인트가 부족해 추가 생성할 수 없습니다.",
                        "error_code": "POINTS_INSUFFICIENT",
                        "generation_count": jd_analysis.generation_count,
                        "max_generations": MAX_QUESTION_GENERATIONS,
                    },
                    status=402,
                )
            except ValueError as exc:
                return Response({"error": str(exc), "error_code": "POINT_POLICY_BLOCKED"}, status=400)

        try:
            # ── GitHub URL 수집 (우선순위 순서: 세션 저장값 > 이력서 > 프로젝트 경험) ──
            github_url = None
            if session.resume and session.resume.github_url:
                github_url = session.resume.github_url
            else:
                from apps.input.models import ProjectExperience
                pe = ProjectExperience.objects.filter(
                    user=session.user, github_url__isnull=False
                ).first()
                if pe:
                    github_url = pe.github_url

            # ── GitHub 분석 실행 (이미 캐시된 결과 있으면 재사용) ──
            github_summary = jd_analysis.github_summary
            if github_url and not github_summary:
                try:
                    from apps.analysis.services.github_service import extract_interview_context
                    gh_result = extract_interview_context(github_url)
                    if gh_result["ok"]:
                        github_summary = gh_result["data"]
                        jd_analysis.github_url     = github_url
                        jd_analysis.github_summary = github_summary
                        jd_analysis.save(update_fields=["github_url", "github_summary"])
                    else:
                        logger.warning("[Analysis] GitHub 분석 실패: %s", gh_result["error_code"])
                except Exception as e:
                    logger.warning("[Analysis] GitHub 분석 중 예외 발생: %s", e)
                # 실패해도 질문 생성은 계속 진행

            # ── GitHub 컨텍스트 문자열 조립 ──
            github_context = ""
            if github_summary:
                lines = ["=== GitHub 프로젝트 기반 추가 컨텍스트 ==="]
                if github_summary.get("project_name"):
                    lines.append(f"프로젝트명: {github_summary['project_name']}")
                if github_summary.get("project_overview"):
                    lines.append(f"개요: {github_summary['project_overview']}")
                if github_summary.get("tech_stack"):
                    lines.append(f"기술 스택: {', '.join(github_summary['tech_stack'])}")
                if github_summary.get("key_features"):
                    lines.append("핵심 기능:")
                    lines.extend([f"  - {f}" for f in github_summary["key_features"]])
                if github_summary.get("technical_challenges"):
                    lines.append("기술적 도전:")
                    lines.extend([f"  - {c}" for c in github_summary["technical_challenges"]])
                if github_summary.get("architecture"):
                    lines.append(f"아키텍처: {github_summary['architecture']}")
                if github_summary.get("interview_points"):
                    lines.append("면접 포인트:")
                    lines.extend([f"  - {p}" for p in github_summary["interview_points"]])
                lines.append("==========================================")
                github_context = "\n".join(lines)

            # ── 기업 맞춤형 컨텍스트 조립 ──
            company_context = ""
            company_name = session.company_name
            if company_name:
                try:
                    from apps.analysis.services.company_service import (
                        classify_company, resolve_industry, build_company_context,
                    )
                    company_type = classify_company(company_name)
                    # extract_jd_requirements()가 분석 단계에서 이미 추출한 industry를
                    # 재사용한다 (없거나 무효할 때만 resolve_industry가 새로 AI를 호출).
                    # jd_keywords는 구형 list 형식으로 저장된 레거시 데이터일 수 있어 dict인 경우만 조회한다.
                    _jd_kw = jd_analysis.jd_keywords
                    stored_requirements = (_jd_kw.get("requirements") or {}) if isinstance(_jd_kw, dict) else {}

                    industry = None
                    recent_trends = ""
                    if company_type == "sme":
                        industry = resolve_industry(stored_requirements.get("industry"), session.jd_text or "")
                    else:
                        try:
                            from apps.analysis.services.trend_service import get_company_recent_trends
                            recent_trends = get_company_recent_trends(company_name)
                        except Exception as e:
                            logger.warning("[AnalysisQuestions] 최근 동향 조회 실패: %s", e)

                    # ── 인재상 조회 우선순위 ──────────────────────────────
                    confirmed_traits = []
                    talent_source    = None
                    talent_summary   = ""

                    # 1순위: 사용자 확정 인재상
                    try:
                        jd_talent_profile = session.jd.custom_talent_profile
                        if jd_talent_profile.confirmed_by_user and jd_talent_profile.items.exists():
                            confirmed_traits = list(
                                jd_talent_profile.items
                                .select_related("trait__category")
                                .order_by("priority_order")
                            )
                            talent_source  = jd_talent_profile.source_type
                            talent_summary = jd_talent_profile.custom_summary or ""
                    except Exception:
                        pass

                    # 2순위: JD 텍스트에서 LLM으로 인재상 자동 추출
                    if not confirmed_traits:
                        try:
                            from apps.input.models import TalentProfileTrait as _Trait
                            from .services.utils import get_client as _get_client
                            from .services.analysis_prompt import build_talent_trait_extract_user
                            import json as _json

                            trait_catalog = list(
                                _Trait.objects.filter(is_active=True)
                                .values_list("trait_code", "trait_name")
                            )
                            catalog_str = "\n".join(f"{code}: {name}" for code, name in trait_catalog)
                            _client = _get_client()
                            _resp = _client.chat.completions.create(
                                model="gpt-4o-mini",
                                temperature=0,
                                messages=[{
                                    "role": "user",
                                    "content": build_talent_trait_extract_user(catalog_str, session.jd_text or ""),
                                }],
                            )
                            codes = _json.loads(_resp.choices[0].message.content.strip())
                            if isinstance(codes, list) and codes:
                                code_map = {t.trait_code: t for t in _Trait.objects.filter(
                                    trait_code__in=codes, is_active=True
                                ).select_related("category")}
                                extracted = []
                                for idx, code in enumerate(codes, start=1):
                                    if code in code_map:
                                        trait_obj = code_map[code]
                                        # priority_order를 가진 임시 객체 구성
                                        extracted.append(type("_Item", (), {
                                            "trait": trait_obj,
                                            "priority_order": idx,
                                            "custom_description": "",
                                        })())
                                if extracted:
                                    confirmed_traits = extracted
                                    talent_source    = "AI_EXTRACTED"
                        except Exception as e:
                            logger.warning("[AnalysisQuestions] LLM 인재상 추출 실패: %s", e)

                    # 3순위: 업종 기반 IndustryTalentProfile fallback
                    # (해당 업종 검색 실패 시 기본 업종으로 재검색하는 fallback은
                    #  get_industry_talent_keywords 내부에서 처리한다)
                    if not confirmed_traits:
                        try:
                            from apps.analysis.services.company_service import get_industry_talent_keywords
                            from apps.input.models import TalentProfileTrait as _Trait
                            _industry = industry or resolve_industry(
                                stored_requirements.get("industry"), session.jd_text or ""
                            )
                            _keywords, _matched_industry = get_industry_talent_keywords(_industry)
                            if _keywords:
                                fallback_traits = list(
                                    _Trait.objects.filter(
                                        trait_name__in=_keywords, is_active=True
                                    ).select_related("category")[:3]
                                )
                                if fallback_traits:
                                    confirmed_traits = [
                                        type("_Item", (), {
                                            "trait": t,
                                            "priority_order": idx,
                                            "custom_description": "",
                                        })()
                                        for idx, t in enumerate(fallback_traits, start=1)
                                    ]
                                    talent_source = "JOB_DEFAULT"
                        except Exception as e:
                            logger.warning("[AnalysisQuestions] IndustryTalentProfile fallback 실패: %s", e)

                    # 4순위: 빈 상태로 진행 (confirmed_traits=[], talent_source=None)
                    # ────────────────────────────────────────────────────────

                    company_context = build_company_context(
                        company_name=company_name,
                        company_type=company_type,
                        industry=industry,
                        confirmed_traits=confirmed_traits,
                        talent_source=talent_source,
                        talent_summary=talent_summary,
                        recent_trends=recent_trends,
                    )

                    session.company_type    = company_type
                    session.company_context = company_context
                    session.selected_talent_keywords = [
                        {"trait_code": item.trait.trait_code, "source": talent_source}
                        for item in confirmed_traits
                    ]
                    session.save(update_fields=["company_type", "company_context", "selected_talent_keywords"])

                except Exception as e:
                    logger.warning("기업 맞춤형 컨텍스트 생성 실패: %s", e)

            # 재생성 시 직전 질문을 프롬프트에 넘겨 "다르게" 생성하도록 유도할 수 있음 (추후)
            combined_context = "\n\n".join(filter(None, [company_context, github_context]))
            questions = generate_all_questions(
                job_role=session.job_role,
                company_name=session.company_name,
                jd_keywords=jd_analysis.jd_keywords,
                resume_analysis=jd_analysis.resume_analysis,
                jd_text=session.jd_text,
                resume_text=session.resume_text,
                cover_letter_text=session.cover_letter_text,
                github_context=combined_context,
            )
            existing_texts = list(
                jd_analysis.questions.values_list("question_text", flat=True)
            )
            output_guard = OutputGuardrail()
            questions = output_guard.filter(
                questions=questions,
                existing_questions=existing_texts,
            )
            db_records = to_db_records(questions, str(jd_analysis.id))
            with transaction.atomic():
                if regenerate:
                    jd_analysis.questions.all().delete()   # 기존 질문 교체
                GeneratedQuestion.objects.bulk_create([
                    GeneratedQuestion(
                        jd_analysis=jd_analysis,
                        question_type=r["question_type"],
                        question_text=r["question_text"],
                        source=r["source"],
                        source_ref=r["source_ref"],
                        answer=r["answer"],
                        order=r["order"],
                    )
                    for r in db_records
                ])
                # 원자적 증가 (더블클릭 이중 카운트 방지)
                JdAnalysis.objects.filter(id=jd_analysis.id).update(
                    generation_count=F("generation_count") + 1
                )

            # 포인트를 냈는데 결과가 0건이면 자동 환불 (사용자 귀책 아님)
            if point_charge is not None and point_charge.created and not db_records:
                refund_points(
                    user=request.user,
                    amount=abs(point_charge.history.amount),
                    reason_code="ANALYSIS.EXTRA_QUESTION_GEN.REFUND",
                    reference_id=str(jd_analysis.id),
                    idempotency_key=f"{point_idempotency_key}:REFUND",
                    description="질문 생성 결과 0건으로 자동 환불",
                )
                point_charge = None
        except Exception as e:
            logger.error("[Analysis] 질문 생성 실패 session=%s: %s", session_id, e, exc_info=True)
            if point_charge is not None and point_charge.created:
                refund_points(
                    user=request.user,
                    amount=abs(point_charge.history.amount),
                    reason_code="ANALYSIS.EXTRA_QUESTION_GEN.REFUND",
                    reference_id=str(jd_analysis.id),
                    idempotency_key=f"{point_idempotency_key}:REFUND",
                    description="질문 생성 실패로 자동 환불",
                )
            return Response({"error": "질문 생성 중 오류가 발생했습니다."}, status=500)

        jd_analysis.refresh_from_db(fields=["generation_count"])
        payload = self._payload(jd_analysis, self._serialize(jd_analysis))
        if point_charge is not None and point_charge.created:
            payload["point_charged"]  = abs(point_charge.history.amount)
            payload["point_balance"]  = point_charge.history.balance_after
        return Response(payload)


class QuestionFeedbackView(APIView):
    """
    예상 질문/답변 만족도 신호 저장 (👍/👎).

    POST /api/v1/analysis/feedback/
        { "session_id": 1, "rating": "up" | "down", "comment": "(선택)" }

    피드백 시점의 generation_count를 함께 저장해 "몇 번째 생성에 만족했는지"를 남긴다.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        rating     = request.data.get("rating")
        comment    = request.data.get("comment", "") or ""

        if rating not in ("up", "down"):
            return Response({"error": "rating은 'up' 또는 'down'이어야 합니다."}, status=400)

        try:
            session = AnalysisSession.objects.get(id=session_id, user=request.user)
        except AnalysisSession.DoesNotExist:
            return Response({"error": "세션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        if not session.jd_analysis_id:
            return Response({"error": "분석이 아직 완료되지 않았습니다."}, status=400)

        try:
            jd_analysis = JdAnalysis.objects.get(id=session.jd_analysis_id)
        except JdAnalysis.DoesNotExist:
            return Response({"error": "분석 결과를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        QuestionFeedback.objects.create(
            jd_analysis=jd_analysis,
            rating=rating,
            generation_count=jd_analysis.generation_count,
            comment=comment[:1000],
        )
        return Response({"ok": True}, status=201)


class TalentCatalogView(APIView):
    """인재상 카탈로그 전체 조회. 인증 불필요."""

    permission_classes = [AllowAny]

    def get(self, request):
        categories = (
            TalentProfileCategory.objects
            .filter(is_active=True)
            .prefetch_related(
                Prefetch("traits", queryset=TalentProfileTrait.objects.filter(is_active=True))
            )
            .order_by("display_order")
        )
        serializer = TalentProfileCategorySerializer(categories, many=True)
        return Response(serializer.data)


class JDTalentProfileView(APIView):
    """JD별 인재상 설정 조회 및 저장."""

    permission_classes = [IsAuthenticated]

    def _get_jd(self, request, jd_id):
        try:
            return JobDescription.objects.get(id=jd_id, user=request.user)
        except JobDescription.DoesNotExist:
            return None

    def get(self, request, jd_id):
        jd = self._get_jd(request, jd_id)
        if jd is None:
            return Response({"error": "JD를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        try:
            profile = jd.custom_talent_profile
        except JDTalentProfile.DoesNotExist:
            return Response({"error": "인재상 설정이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        serializer = JDTalentProfileSerializer(profile)
        return Response(serializer.data)

    def put(self, request, jd_id):
        jd = self._get_jd(request, jd_id)
        if jd is None:
            return Response({"error": "JD를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        data        = request.data
        source_type = data.get("source_type", "USER_DEFINED")
        items_data  = data.get("items", [])

        # 검증
        valid_source_types = {"OFFICIAL", "AI_EXTRACTED", "USER_DEFINED", "JOB_DEFAULT", "HYBRID"}
        if source_type not in valid_source_types:
            return Response({"error": "유효하지 않은 source_type입니다."}, status=400)

        if not (1 <= len(items_data) <= 5):
            return Response({"error": "인재상은 1개 이상 5개 이하로 선택해야 합니다."}, status=400)

        trait_codes    = [i.get("trait_code") for i in items_data]
        priority_orders = [i.get("priority_order") for i in items_data]

        if len(set(trait_codes)) != len(trait_codes):
            return Response({"error": "trait_code가 중복됩니다."}, status=400)

        if len(set(priority_orders)) != len(priority_orders):
            return Response({"error": "priority_order가 중복됩니다."}, status=400)

        for po in priority_orders:
            if not isinstance(po, int) or not (1 <= po <= 5):
                return Response({"error": "priority_order는 1~5 범위여야 합니다."}, status=400)

        # trait 존재·활성 여부 확인
        trait_map = {
            t.trait_code: t
            for t in TalentProfileTrait.objects.filter(trait_code__in=trait_codes, is_active=True)
        }
        for code in trait_codes:
            if code not in trait_map:
                return Response({"error": f"유효하지 않거나 비활성 trait_code: {code}"}, status=400)

        for item in items_data:
            desc = item.get("custom_description", "")
            if len(desc) > 500:
                return Response({"error": "custom_description은 500자 이하여야 합니다."}, status=400)
            weight = item.get("weight")
            if weight is not None:
                try:
                    w = float(weight)
                    if not (0 <= w <= 100):
                        raise ValueError
                except (TypeError, ValueError):
                    return Response({"error": "weight는 0~100 범위여야 합니다."}, status=400)

        confirmed_by_user = bool(data.get("confirmed_by_user", False))
        if source_type == "USER_DEFINED" and not confirmed_by_user:
            return Response({"error": "USER_DEFINED 저장 시 confirmed_by_user가 True여야 합니다."}, status=400)

        # 저장 (전체 교체)
        with transaction.atomic():
            profile, _ = JDTalentProfile.objects.get_or_create(
                jd=jd,
                defaults={"source_type": source_type},
            )
            profile.source_type      = source_type
            profile.source_text      = data.get("source_text")
            profile.custom_summary   = data.get("custom_summary")
            profile.confirmed_by_user = confirmed_by_user
            if confirmed_by_user:
                profile.confirmed_at = timezone.now()
            profile.save()

            profile.items.all().delete()
            for item in items_data:
                JDTalentProfileItem.objects.create(
                    jd_talent_profile=profile,
                    trait=trait_map[item["trait_code"]],
                    priority_order=item["priority_order"],
                    custom_description=item.get("custom_description", ""),
                    weight=item.get("weight"),
                )

        serializer = JDTalentProfileSerializer(profile)
        return Response(serializer.data)
