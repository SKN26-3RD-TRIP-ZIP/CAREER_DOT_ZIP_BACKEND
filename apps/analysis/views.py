import threading
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import AnalysisSession, GeneratedQuestion
from .services import extract_jd_keywords, analyze_resume, generate_all_questions


def _run_analysis(session_id: int):
    """백그라운드 스레드에서 실행되는 전체 분석 파이프라인."""
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

        # 3) 예상 질문 생성
        questions = generate_all_questions(
            job_role=session.job_role,
            company_name=session.company_name,
            jd_keywords=keywords,
            resume_analysis=resume_summary,
        )

        # 4) 질문 DB 저장 — bulk_create로 단건 INSERT 방지
        GeneratedQuestion.objects.bulk_create([
            GeneratedQuestion(
                session=session,
                question_type=q["type"],
                question_text=q["text"],
                order=i,
            )
            for i, q in enumerate(questions)
        ])

        session.status = "ready"
        session.save(update_fields=["status", "updated_at"])

    except Exception as e:
        session.status = "failed"
        session.save(update_fields=["status", "updated_at"])
        raise e


class AnalysisStartView(APIView):
    """
    POST /api/analysis/start/
    입력 데이터 저장 후 백그라운드 분석 시작. 즉시 session_id 반환.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session = AnalysisSession.objects.create(
            user=request.user,
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
    GET /api/analysis/<session_id>/status/
    프론트가 2~3초마다 폴링. "ready" 또는 "failed" 되면 폴링 중단.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = AnalysisSession.objects.get(id=session_id, user=request.user)
        return Response({
            "status": session.status,
            "jd_keywords": session.jd_keywords if session.status == "ready" else [],
        })


class AnalysisResultView(APIView):
    """
    GET /api/analysis/<session_id>/result/
    분석 완료 후 전체 결과 + 생성된 질문 목록 반환.
    interview 앱에서 이 API를 호출해 질문을 가져간다.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = AnalysisSession.objects.get(id=session_id, user=request.user)

        if session.status != "ready":
            return Response(
                {"error": "분석이 아직 완료되지 않았습니다.", "status": session.status},
                status=400,
            )

        questions = list(
            session.questions.values("id", "question_type", "question_text", "order")
        )

        return Response({
            "session_id":      session.id,
            "job_role":        session.job_role,
            "company_name":    session.company_name,
            "jd_keywords":     session.jd_keywords,
            "resume_analysis": session.resume_analysis,
            "questions":       questions,
        })
