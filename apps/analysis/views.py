import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import connection

from .models import AnalysisSession, JdAnalysis, GeneratedQuestion
from apps.input.models import JobDescription, ResumeMaster, CoverLetter
from .serializers import (
    JDListSerializer, ResumeListSerializer, CoverLetterListSerializer,
    ResumeFullCreateSerializer,
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
from .services.question_rag_service    import search_similar_questions
from .services.question_gen_service    import generate_questions
from .services.question_merge_service  import merge_and_deduplicate
from .services.star_service            import generate_star_answers
from .services.question_output_service import build_question_output, to_db_records

logger = logging.getLogger(__name__)


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
            f_jd_req = executor.submit(extract_jd_requirements, session.jd_text)
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

        # Step 2: match_score(임베딩+LLM) ↔ RAG검색+질문생성(LLM) 병렬
        # generate_questions는 jd_kw + resume_summary만 필요하므로 match_result를 기다릴 필요 없음
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            f_match = executor.submit(
                calculate_match_score,
                jd_keywords=jd_kw,
                resume_analysis=resume_summary,
                cover_letter_text=session.cover_letter_text,
                career_level=inferred_level,
                jd_requirements=jd_req,
                job_role=session.job_role,
            )
            f_rag = executor.submit(search_similar_questions, jd_kw, 20)
            f_llm = executor.submit(
                generate_questions,
                job_role=session.job_role,
                company_name=session.company_name,
                jd_keywords=jd_kw,
                resume_analysis=resume_summary,
            )

        match_result_raw, err_match = _resolve_future(f_match, "매칭 점수 계산", {})
        rag_questions,    _         = _resolve_future(f_rag,   "RAG 질문 검색",  [])
        llm_questions,    _         = _resolve_future(f_llm,   "LLM 질문 생성",  [])
        logger.info("[TIMING] step2 병렬(match+RAG+question_gen): %.2fs", time.time() - t0)

        if err_match:
            raise RuntimeError("매칭 점수 계산 실패로 파이프라인을 중단합니다.")

        match_result = build_match_result(match_result_raw, inferred_level)

        # Step 3: gap 계산(순수 로직) ↔ 질문 merge(임베딩) 병렬
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_gap   = executor.submit(
                calculate_gap,
                jd_keywords=jd_kw,
                jd_requirements=jd_req,
                resume_analysis=resume_summary,
                unmatched_keywords=match_result["unmatched_keywords"],
                trait_details=match_result.get("trait_details"),
            )
            f_merge = executor.submit(merge_and_deduplicate, rag_questions, llm_questions)

        gap_result, _ = _resolve_future(f_gap,   "갭 계산",       {})
        questions,  _ = _resolve_future(f_merge, "질문 통합/중복 제거", [])
        gap_message   = build_gap_message(gap_result, inferred_level)
        logger.info("[TIMING] step3 병렬(gap+merge): %.2fs", time.time() - t0)

        # Step 4: STAR 답안 생성 — 타입별 3그룹 병렬
        t0 = time.time()
        star_groups = {
            "personality": [q for q in questions if q.get("type") == "personality"],
            "technical":   [q for q in questions if q.get("type") == "technical"],
            "experience":  [q for q in questions if q.get("type") == "experience"],
        }
        star_kwargs = dict(
            job_role=session.job_role,
            company_name=session.company_name,
            jd_text=session.jd_text,
            resume_text=session.resume_text,
            cover_letter_text=session.cover_letter_text,
        )
        with ThreadPoolExecutor(max_workers=3) as executor:
            star_futures = {
                qtype: executor.submit(generate_star_answers, questions=qs, **star_kwargs)
                for qtype, qs in star_groups.items()
                if qs
            }

        questions_with_star = []
        for qtype, f in star_futures.items():
            group_result, err = _resolve_future(f, f"STAR 생성({qtype})", [])
            questions_with_star.extend(group_result)
        logger.info("[TIMING] step4 STAR 3그룹 병렬: %.2fs", time.time() - t0)

        questions = build_question_output(questions_with_star)

        # Step 5: JdAnalysis 생성
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

        # 7) 질문 DB 저장
        db_records = to_db_records(questions, str(jd_analysis.id))
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

        # input.JobDescription에 분석 결과 반영
        summary_parts = []
        if jd_req.get("job_type"):
            summary_parts.append(jd_req["job_type"])
        if jd_req.get("min_years"):
            summary_parts.append(f"경력 {jd_req['min_years']}년 이상")
        if jd_req.get("education") and jd_req["education"] != "무관":
            summary_parts.append(jd_req["education"])
        if jd_req.get("required_tech"):
            summary_parts.append(", ".join(jd_req["required_tech"][:5]))
        company_summary = " | ".join(summary_parts) if summary_parts else session.job_role

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

        try:
            jd = JobDescription.objects.get(id=jd_id, user=request.user)
        except JobDescription.DoesNotExist:
            return Response({"error": "JD를 찾을 수 없습니다."}, status=400)

        try:
            resume = ResumeMaster.objects.get(id=resume_id, user=request.user)
        except ResumeMaster.DoesNotExist:
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
                pass

        session = AnalysisSession.objects.create(
            user=request.user,
            jd_id=jd_id,
            resume_id=resume_id,
            cover_letter_id=cover_letter_id,
            job_role=jd.position,
            company_name=jd.company_name,
            jd_text=jd.original_text or "",
            resume_text=resume.original_text or "",
            cover_letter_text=cover_letter_text,
            career_level=career_level,
            status="analyzing",
        )

        threading.Thread(
            target=_run_analysis,
            args=(session.id,),
            daemon=True,
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
            "cl_points":       [...],
            "questions": [
                {
                    "id":            "uuid",
                    "question_type": "technical",
                    "question_text": "...",
                    "answer":        { "summary": "...", "situation": "...", ... },
                    "order":         0
                },
                ...
            ]
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

        jd_analysis = JdAnalysis.objects.get(id=session.jd_analysis_id)
        questions = list(
            jd_analysis.questions.values(
                "id", "question_type", "question_text", "answer", "order"
            )
        )

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
            "questions":           questions,
        })
