import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import connection

from .models import AnalysisSession, JdAnalysis, GeneratedQuestion
from .services import extract_jd_keywords, analyze_resume, generate_all_questions
from .services.jd_service     import extract_jd_requirements
from .services.match_service  import calculate_match_score
from .services.result_service import build_match_result
from .services.gap_service    import calculate_gap, build_gap_message
from .services.question_output_service import to_db_records

logger = logging.getLogger(__name__)


def _run_analysis(session_id: int):
    """
    백그라운드 스레드에서 실행되는 전체 분석 파이프라인.

    1) JD 키워드 추출
    2) 이력서·자소서 분석
    3) 매칭 점수 및 강점/약점 계산
    4) JdAnalysis 생성
    5) 질문 + STAR 답안 생성 → GeneratedQuestion 저장
    """
    session = AnalysisSession.objects.get(id=session_id)
    try:
        # 1) JD 키워드 추출 / JD 자격 요건 추출 / 이력서 분석 — 3개 병렬 실행
        with ThreadPoolExecutor(max_workers=3) as executor:
            f_jd_kw  = executor.submit(extract_jd_keywords,    session.jd_text)
            f_jd_req = executor.submit(extract_jd_requirements, session.jd_text)
            f_resume = executor.submit(analyze_resume, session.resume_text, session.cover_letter_text)
            jd_kw          = f_jd_kw.result()
            jd_req         = f_jd_req.result()
            resume_summary = f_resume.result()

        inferred_level = resume_summary.get("career_level", session.career_level)
        session.jd_keywords     = {**jd_kw, "requirements": jd_req}
        session.resume_analysis = resume_summary
        session.career_level    = inferred_level
        session.save(update_fields=["jd_keywords", "resume_analysis", "career_level"])

        # 3) 매칭 점수 및 강점/약점/자소서 포인트 계산
        match_result = calculate_match_score(
            jd_keywords=jd_kw,
            resume_analysis=resume_summary,
            cover_letter_text=session.cover_letter_text,
            career_level=inferred_level,
            jd_requirements=jd_req,
            job_role=session.job_role,
        )
        match_result = build_match_result(match_result, inferred_level)

        # 4) 갭 분석
        gap_result  = calculate_gap(
            jd_keywords=jd_kw,
            jd_requirements=jd_req,
            resume_analysis=resume_summary,
            unmatched_keywords=match_result["unmatched_keywords"],
            trait_details=match_result.get("trait_details"),
        )
        gap_message = build_gap_message(gap_result, inferred_level)

        # 5) JdAnalysis 생성
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

        # 6) 질문 + STAR 답안 생성
        questions = generate_all_questions(
            job_role=session.job_role,
            company_name=session.company_name,
            jd_keywords=jd_kw,
            resume_analysis=resume_summary,
            jd_text=session.jd_text,
            resume_text=session.resume_text,
            cover_letter_text=session.cover_letter_text,
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

        # 세션에 jd_analysis_id 저장 후 완료
        session.jd_analysis_id = jd_analysis.id
        session.status = "ready"
        session.save(update_fields=["jd_analysis_id", "status", "updated_at"])

    except Exception as e:
        session.status = "failed"
        session.save(update_fields=["status", "updated_at"])
        logger.error("Analysis failed for session %s: %s", session_id, e, exc_info=True)
    finally:
        connection.close()


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
        session = AnalysisSession.objects.create(
            user=request.user,
            jd_id=request.data.get("jd_id"),
            resume_id=request.data.get("resume_id"),
            cover_letter_id=request.data.get("cover_letter_id"),
            job_role=request.data.get("job_role", ""),
            company_name=request.data.get("company_name", ""),
            jd_text=request.data.get("jd_text", ""),
            resume_text=request.data.get("resume_text", ""),
            cover_letter_text=request.data.get("cover_letter_text", ""),
            career_level=request.data.get("career_level", "entry"),  # "entry" | "experienced"
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
