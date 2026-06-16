import logging

from django.http import HttpResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from apps.interview.models import InterviewSession
from apps.evaluation.models import AnswerWeaknessTag
from .models import FinalReport
from .serializers import FinalReportSerializer, FinalReportListSerializer, FinalReportSessionSerializer
from .services.report_generator import generate_final_report
from .services.recommendation_service import (
    get_recommended_questions_for_tags,
    get_session_weakness_recommended_questions,
)
from .services.pdf_generator import generate_report_pdf

logger = logging.getLogger("feedback_ai.report_views")


class ReportGenerationFailed(RuntimeError):
    pass


def is_failed_report_summary(summary):
    metadata = (summary or {}).get("evaluation_metadata", {})
    answer_count = int(metadata.get("answer_count") or 0)
    evaluated_count = int(metadata.get("evaluated_answer_count") or 0)
    return answer_count > 0 and evaluated_count == 0


def report_generation_failed_response():
    return Response(
        {
            "detail": "리포트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            "code": "AI_REPORT_GENERATION_FAILED",
            "error_code": "AI_REPORT_GENERATION_FAILED",
            "retryable": True,
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _get_existing_report(session):
    try:
        return session.final_report
    except (FinalReport.DoesNotExist, AttributeError):
        return None


def _check_evaluation_failure(report):
    summary = report.summary or {}
    metadata = summary.get("evaluation_metadata", {})
    return metadata.get("answer_count", 0) > 0 and metadata.get("evaluated_answer_count", 0) == 0


def _create_report(session):
    # 동시 GET 요청이 같은 세션 리포트를 중복 생성하거나 IntegrityError를 내는 것을
    # 막기 위해 세션 행에 select_for_update 락을 건다. 이미 생성됐으면 그대로 반환.
    with transaction.atomic():
        InterviewSession.objects.select_for_update().get(pk=session.pk)
        existing = FinalReport.objects.filter(session=session).first()
        if existing:
            return existing
        summary = generate_final_report(session)
        if is_failed_report_summary(summary):
            raise ReportGenerationFailed()
        return FinalReport.objects.create(session=session, summary=summary)


def _build_session_report_response(session):
    report = _get_existing_report(session)
    if report and _check_evaluation_failure(report):
        report.delete()
        report = None

    if not report:
        try:
            report = _create_report(session)
        except ReportGenerationFailed:
            return report_generation_failed_response()
        except Exception:
            return report_generation_failed_response()

    serializer = FinalReportSessionSerializer(report)
    return Response(serializer.data, status=status.HTTP_200_OK)


class FinalReportGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_session(self, session_id):
        try:
            return InterviewSession.objects.get(id=session_id, user=self.request.user)
        except InterviewSession.DoesNotExist:
            return None

    def post(self, request, session_id):
        session = self.get_session(session_id)
        if not session:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

        force = request.data.get("force_regenerate", False)
        try:
            report = session.final_report
        except FinalReport.DoesNotExist:
            report = None

        if report and is_failed_report_summary(report.summary):
            report.delete()
            report = None

        if report and not force:
            serializer = FinalReportSerializer(report)
            return Response(serializer.data, status=status.HTTP_200_OK)

        try:
            with transaction.atomic():
                # 동시 강제재생성 경합 방지: 세션 행에 락을 걸고 락 안에서 리포트 재확인.
                InterviewSession.objects.select_for_update().get(pk=session.pk)
                report = FinalReport.objects.filter(session=session).first()
                summary = generate_final_report(session)
                if is_failed_report_summary(summary):
                    raise ReportGenerationFailed()
                is_new = report is None
                if report:
                    report.summary = summary
                    report.save(update_fields=["summary"])
                else:
                    report = FinalReport.objects.create(session=session, summary=summary)
        except ReportGenerationFailed:
            return report_generation_failed_response()
        except Exception:
            return report_generation_failed_response()

        serializer = FinalReportSerializer(report)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )


class FinalReportDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_report(self, session_id):
        try:
            session = InterviewSession.objects.get(id=session_id, user=self.request.user)
            return session.final_report
        except (InterviewSession.DoesNotExist, FinalReport.DoesNotExist, AttributeError):
            return None

    def get(self, request, session_id):
        report = self.get_report(session_id)
        if not report:
            return Response({"detail": "Report not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = FinalReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FinalReportListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        reports = (
            FinalReport.objects
            .filter(session__user=request.user)
            .select_related("session")
            .order_by("-generated_at")
        )
        serializer = FinalReportListSerializer(reports, many=True)
        return Response({"total": reports.count(), "results": serializer.data}, status=status.HTTP_200_OK)


class LatestSessionReportView(APIView):
    """GET /sessions/latest/report"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        session = (
            InterviewSession.objects
            .filter(user=request.user, status="completed")
            .order_by("-created_at")
            .first()
        )
        if not session:
            return Response({"detail": "No completed session found."}, status=status.HTTP_404_NOT_FOUND)
        return _build_session_report_response(session)


class SessionFinalReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_session(self, session_id):
        try:
            return InterviewSession.objects.get(id=session_id, user=self.request.user)
        except InterviewSession.DoesNotExist:
            return None

    def get(self, request, session_id):
        session = self.get_session(session_id)
        if not session:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)
        if session.status != "completed":
            return Response(
                {"detail": "Report can be generated only after the session is completed."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _build_session_report_response(session)


# E7.9 -- 약점 태그 기반 추천 질문
class WeaknessRecommendedQuestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_session(self, session_id):
        try:
            return InterviewSession.objects.get(id=session_id, user=self.request.user)
        except InterviewSession.DoesNotExist:
            return None

    def get(self, request, session_id):
        session = self.get_session(session_id)
        if not session:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

        limit = int(request.query_params.get("limit", 10))
        result = get_session_weakness_recommended_questions(session, total_limit=limit)
        return Response(
            {
                "session_id": str(session.id),
                "weakness_tags": result["weakness_tags"],
                "recommended_questions": result["recommended_questions"],
                "total": len(result["recommended_questions"]),
            },
            status=status.HTTP_200_OK,
        )


class TagRecommendedQuestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tag_names = request.data.get("weakness_tags", [])
        if not isinstance(tag_names, list) or not tag_names:
            return Response({"detail": "weakness_tags 배열이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        limit = int(request.data.get("limit", 10))
        limit_per_tag = int(request.data.get("limit_per_tag", 3))
        questions = get_recommended_questions_for_tags(
            weakness_tag_names=tag_names,
            limit_per_tag=limit_per_tag,
            total_limit=limit,
        )
        return Response(
            {
                "weakness_tags": tag_names,
                "recommended_questions": questions,
                "total": len(questions),
            },
            status=status.HTTP_200_OK,
        )


# E7.12 -- PDF 다운로드
class ReportPDFDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_session(self, session_id):
        try:
            return InterviewSession.objects.get(id=session_id, user=self.request.user)
        except InterviewSession.DoesNotExist:
            return None

    def get(self, request, session_id):
        session = self.get_session(session_id)
        if not session:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

        report = _get_existing_report(session)
        if report and _check_evaluation_failure(report):
            report.delete()
            report = None

        if not report:
            try:
                report = _create_report(session)
            except ReportGenerationFailed:
                return report_generation_failed_response()
            except Exception as exc:
                logger.exception("PDF용 리포트 생성 중 오류: %s", exc)
                return report_generation_failed_response()

        try:
            pdf_bytes = generate_report_pdf(report)
        except Exception as exc:
            logger.exception("PDF 렌더링 오류 (session=%s): %s", session_id, exc)
            return Response(
                {"detail": "PDF 생성에 실패했습니다.", "code": "PDF_GENERATION_FAILED"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        filename = f"career_zip_report_{session_id}.pdf"
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = len(pdf_bytes)
        return resp
