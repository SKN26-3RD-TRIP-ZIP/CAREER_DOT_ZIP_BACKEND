import threading
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import AnalysisSession, JdAnalysis, GeneratedQuestion
from .services import extract_jd_keywords, analyze_resume, generate_all_questions
from .services.match_service import calculate_match_score


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
        # 1) JD 키워드 추출
        keywords = extract_jd_keywords(session.jd_text)
        session.jd_keywords = keywords
        session.save(update_fields=["jd_keywords"])

        # 2) 이력서·자소서 분석
        resume_summary = analyze_resume(session.resume_text, session.cover_letter_text)
        session.resume_analysis = resume_summary
        session.save(update_fields=["resume_analysis"])

        # 3) 매칭 점수 및 강점/약점/자소서 포인트 계산
        match_result = calculate_match_score(
            jd_keywords=keywords,
            resume_analysis=resume_summary,
            cover_letter_text=session.cover_letter_text,
        )

        # 4) JdAnalysis 생성
        jd_analysis = JdAnalysis.objects.create(
            user=session.user,
            jd_id=session.jd_id,
            resume_id=session.resume_id,
            cover_letter_id=session.cover_letter_id,
            match_score=match_result["match_score"],
            jd_keywords=keywords,
            resume_analysis=resume_summary,
            strengths=match_result["strengths"],
            weaknesses=match_result["weaknesses"],
            cl_points=match_result["cl_points"],
        )

        # 5) 질문 + STAR 답안 생성
        questions = generate_all_questions(
            job_role=session.job_role,
            company_name=session.company_name,
            jd_keywords=keywords,
            resume_analysis=resume_summary,
            jd_text=session.jd_text,
            resume_text=session.resume_text,
            cover_letter_text=session.cover_letter_text,
        )

        # 6) 질문 DB 저장
        GeneratedQuestion.objects.bulk_create([
            GeneratedQuestion(
                jd_analysis=jd_analysis,
                question_type=q["type"],
                question_text=q["text"],
                answer=q.get("answer", {}),
                order=i,
            )
            for i, q in enumerate(questions)
        ])

        # 세션에 jd_analysis_id 저장 후 완료
        session.jd_analysis_id = jd_analysis.id
        session.status = "ready"
        session.save(update_fields=["jd_analysis_id", "status", "updated_at"])

    except Exception as e:
        session.status = "failed"
        session.save(update_fields=["status", "updated_at"])
        raise e


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

        return Response({
            "jd_analysis_id":  str(jd_analysis.id),
            "match_score":     jd_analysis.match_score,
            "jd_keywords":     jd_analysis.jd_keywords,
            "resume_analysis": jd_analysis.resume_analysis,
            "strengths":       jd_analysis.strengths,
            "weaknesses":      jd_analysis.weaknesses,
            "cl_points":       jd_analysis.cl_points,
            "questions":       questions,
        })
