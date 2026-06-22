import logging

from django.http import HttpResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from apps.interview.models import InterviewSession
from apps.evaluation.models import AnswerWeaknessTag
from apps.evaluation.evaluation_chains import EvaluationFormatError
from .models import FinalReport
from .serializers import (
    FinalReportSerializer,
    FinalReportListSerializer,
    FinalReportSessionSerializer,
    RoadmapResponseSerializer,
)
from .services.report_generator import generate_final_report
from .services.recommendation_service import (
    get_recommended_questions_for_tags,
    get_session_weakness_recommended_questions,
)
from .services.pdf_generator import generate_report_pdf
from .services.roadmap_service import get_or_create_roadmap

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


def report_evaluation_format_error_response():
    """LLM 응답 포맷이 재시도까지 소진하고도 깨진 경우의 전용 에러 응답.

    프론트(StateView)가 이 code로 전용 에러 창을 띄울 수 있도록 구분한다.
    """
    return Response(
        {
            "detail": "AI 평가 응답 형식 오류로 채점을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "code": "AI_EVALUATION_FORMAT_ERROR",
            "error_code": "AI_EVALUATION_FORMAT_ERROR",
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
    existing = FinalReport.objects.filter(session=session).first()
    if existing:
        return existing

    # 무거운 generate_final_report(LLM 호출 다수)를 락 안에서 수행한다.
    # 락을 먼저 잡고 재확인해, 동시 요청이 같은 세션 리포트를 중복 생성(=중복 LLM 비용)하는
    # 것을 막는다.
    with transaction.atomic():
        InterviewSession.objects.select_for_update().get(pk=session.pk)
        report = FinalReport.objects.filter(session=session).first()
        if report:
            return report
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
        except EvaluationFormatError:
            logger.exception("리포트 평가 포맷 오류 (session=%s)", getattr(session, "id", "?"))
            return report_evaluation_format_error_response()
        except ReportGenerationFailed:
            return report_generation_failed_response()
        except Exception:
            logger.exception("리포트 생성 실패 (session=%s)", getattr(session, "id", "?"))
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
            # 락을 먼저 잡고 재확인 후 생성한다. generate_final_report(무거운 LLM 호출)를
            # 락 안에서 1회만 수행해 동시 요청의 중복 생성/중복 LLM 비용을 방지.
            with transaction.atomic():
                InterviewSession.objects.select_for_update().get(pk=session.pk)
                report = FinalReport.objects.filter(session=session).first()
                if report and is_failed_report_summary(report.summary):
                    report.delete()
                    report = None

                if report and not force:
                    is_new = False
                else:
                    summary = generate_final_report(session)
                    if is_failed_report_summary(summary):
                        raise ReportGenerationFailed()
                    if report:
                        report.summary = summary
                        report.save(update_fields=["summary"])
                        is_new = False
                    else:
                        report = FinalReport.objects.create(session=session, summary=summary)
                        is_new = True
        except EvaluationFormatError:
            logger.exception("리포트 평가 포맷 오류 (session=%s)", session_id)
            return report_evaluation_format_error_response()
        except ReportGenerationFailed:
            return report_generation_failed_response()
        except Exception:
            logger.exception("리포트 생성 실패 (session=%s)", session_id)
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


class SessionFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    _PERSONA_META = {
        "practical": {"short_name": "실무형", "avatar_emoji": "💼"},
        "coach":     {"short_name": "코치형", "avatar_emoji": "🎯"},
        "verifier":  {"short_name": "검증형", "avatar_emoji": "🔎"},
    }

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
        if not report:
            return Response({"detail": "Report not generated yet."}, status=status.HTTP_404_NOT_FOUND)

        summary        = report.summary or {}
        score_summary  = summary.get("score_summary", {})
        persona_fb     = score_summary.get("persona_feedback", {})
        triggered      = summary.get("dynamically_triggered_tags", {})
        persona_type   = summary.get("evaluation_metadata", {}).get("persona_type", "practical")

        p_meta = self._PERSONA_META.get(persona_type, {"short_name": persona_type, "avatar_emoji": "💼"})

        pros = [
            t.get("description") or t.get("tag_name", "")
            for t in triggered.get("strength_tags", [])[:3]
            if t.get("description") or t.get("tag_name")
        ] or ["분석된 강점 데이터가 없습니다."]

        cons = [
            t.get("description") or t.get("tag_name", "")
            for t in triggered.get("weakness_tags", [])[:3]
            if t.get("description") or t.get("tag_name")
        ] or ["분석된 보완점 데이터가 없습니다."]

        rec_result = get_session_weakness_recommended_questions(session, total_limit=5)
        expected_questions = [
            {"order": i + 1, "text": q["question_text"]}
            for i, q in enumerate(rec_result["recommended_questions"])
        ]

        answer_structure_map = {
            "practical": ["핵심 결론", "수치 근거", "트레이드오프", "결과"],
            "coach":     ["상황", "행동", "배움", "성장"],
            "verifier":  ["주장", "근거", "반례 검토", "결론"],
        }

        return Response(
            {
                "persona": {
                    "short_name": p_meta["short_name"],
                    "avatar_emoji": p_meta["avatar_emoji"],
                    "total_score": report.overall_score or 0,
                    "tags": [persona_fb.get("persona_label", p_meta["short_name"])],
                },
                "summary": " ".join(filter(None, [
                    persona_fb.get("intro", ""),
                    persona_fb.get("closing", ""),
                ])) or "페르소나 피드백을 생성 중입니다.",
                "pros": pros,
                "cons": cons,
                "recommended_answer_structure": answer_structure_map.get(
                    persona_type, ["상황", "과제", "행동", "결과"]
                ),
                "expected_questions": expected_questions,
            },
            status=status.HTTP_200_OK,
        )


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
            except EvaluationFormatError:
                logger.exception("PDF용 리포트 평가 포맷 오류 (session=%s)", session_id)
                return report_evaluation_format_error_response()
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




class SessionRoadmapView(APIView):
    """GET /api/v1/sessions/{session_id}/roadmap

    weakness_tags LLM roadmap. Returns cached DB result if available.
    """
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

        try:
            roadmap = get_or_create_roadmap(session)
        except Exception as exc:
            logger.exception("roadmap generation error (session=%s): %s", session_id, exc)
            return Response(
                {"detail": "roadmap generation failed.", "code": "ROADMAP_GENERATION_FAILED"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        session_count = InterviewSession.objects.filter(user=request.user).count()
        if session_count <= 2:
            target_delta_label = "+2~4"
        elif session_count <= 5:
            target_delta_label = "+3~6"
        else:
            target_delta_label = "+5~10"

        data = {
            "week_priority_text": roadmap["week_priority_text"],
            "target_delta_label": target_delta_label,
            "practice_question": roadmap["practice_question"],
            "items": roadmap["items"],
        }
        serializer = RoadmapResponseSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
