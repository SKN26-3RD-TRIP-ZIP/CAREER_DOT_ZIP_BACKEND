import logging

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from apps.interview.models import InterviewSession
from apps.evaluation.models import AnswerWeaknessTag
from .models import ActionPlan, FinalReport, ReportShareToken
from .serializers import (
    ActionPlanCreateSerializer,
    ActionPlanPatchSerializer,
    ActionPlanSerializer,
    FinalReportSerializer,
    FinalReportListSerializer,
    FinalReportSessionSerializer,
    RoadmapResponseSerializer,
    build_shared_summary,
)
from .services.report_jobs import ensure_report_generation
from .services.recommendation_service import (
    get_recommended_questions_for_tags,
    get_session_weakness_recommended_questions,
)
from .services.pdf_generator import generate_report_pdf
from .services.roadmap_service import get_or_create_roadmap

logger = logging.getLogger("feedback_ai.report_views")


def _positive_int(value, default, max_value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), max_value)


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


def _build_session_report_response(session):
    """폴링 계약: done → 200, processing → 202, failed → 503(retryable).

    무거운 생성은 ensure_report_generation 이 백그라운드 스레드에서 수행한다
    (DB 락/커넥션 장기 점유 없음). 프론트는 done/failed 가 될 때까지 폴링한다.
    """
    report = _get_existing_report(session)
    if report and report.status == FinalReport.STATUS_DONE:
        return Response(FinalReportSessionSerializer(report).data, status=status.HTTP_200_OK)

    try:
        report, _started = ensure_report_generation(session)
    except Exception:
        logger.exception("리포트 생성 트리거 실패 (session=%s)", getattr(session, "id", "?"))
        return report_generation_failed_response()

    if report.status == FinalReport.STATUS_DONE:
        return Response(FinalReportSessionSerializer(report).data, status=status.HTTP_200_OK)
    if report.status == FinalReport.STATUS_FAILED:
        return report_generation_failed_response()
    # processing/pending → 폴링 안내 (202 Accepted)
    return Response(FinalReportSessionSerializer(report).data, status=status.HTTP_202_ACCEPTED)


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

        force = bool(request.data.get("force_regenerate", False))

        report = _get_existing_report(session)
        if report and report.status == FinalReport.STATUS_DONE and not force:
            return Response(FinalReportSerializer(report).data, status=status.HTTP_200_OK)

        try:
            # 상태 선점만 락 안에서 짧게 수행하고, 무거운 LLM 생성은 백그라운드로 위임한다.
            report, started = ensure_report_generation(session, force=force)
        except Exception:
            logger.exception("리포트 생성 트리거 실패 (session=%s)", session_id)
            return report_generation_failed_response()

        if report.status == FinalReport.STATUS_DONE:
            return Response(
                FinalReportSerializer(report).data,
                status=status.HTTP_201_CREATED if started else status.HTTP_200_OK,
            )
        if report.status == FinalReport.STATUS_FAILED:
            return report_generation_failed_response()
        # processing/pending → 클라이언트는 GET 으로 폴링 (202 Accepted)
        return Response(FinalReportSerializer(report).data, status=status.HTTP_202_ACCEPTED)


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


class UserActionPlanListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        page = _positive_int(request.query_params.get("page"), 1, 100000)
        size = _positive_int(request.query_params.get("size"), 20, 100)
        queryset = (
            ActionPlan.objects
            .filter(report__session__user=request.user)
            .select_related("report", "report__session")
            .order_by("-created_at", "-id")
        )
        total = queryset.count()
        offset = (page - 1) * size
        results = queryset[offset:offset + size]
        return Response(
            {
                "total": total,
                "page": page,
                "size": size,
                "results": ActionPlanSerializer(results, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ReportActionPlanCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, report_id):
        report = get_object_or_404(
            FinalReport.objects.select_related("session"),
            id=report_id,
            session__user=request.user,
        )
        if report.action_plans.count() >= 3:
            return Response(
                {"detail": "리포트별 개선 과제는 최대 3개까지 등록할 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ActionPlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action_plan = serializer.save(report=report)
        return Response(ActionPlanSerializer(action_plan).data, status=status.HTTP_201_CREATED)


class ActionPlanPatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, action_plan_id):
        action_plan = get_object_or_404(
            ActionPlan.objects.select_related("report", "report__session"),
            id=action_plan_id,
            report__session__user=request.user,
        )
        serializer = ActionPlanPatchSerializer(action_plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ActionPlanSerializer(action_plan).data, status=status.HTTP_200_OK)


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
                    "total_score": report.overall_score,
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

        # PDF는 완성된(done) 리포트만 렌더링한다. 미완성이면 생성을 트리거하고
        # 폴링을 안내한다(202) — 다운로드 요청에서 수십 초 동기 LLM 생성을 막기 위함.
        report = _get_existing_report(session)
        if not report or report.status != FinalReport.STATUS_DONE:
            try:
                report, _started = ensure_report_generation(session)
            except Exception as exc:
                logger.exception("PDF용 리포트 생성 트리거 오류: %s", exc)
                return report_generation_failed_response()

            if report.status == FinalReport.STATUS_FAILED:
                return report_generation_failed_response()
            if report.status != FinalReport.STATUS_DONE:
                return Response(
                    {
                        "detail": "리포트 생성 중입니다. 완료 후 다시 시도해 주세요.",
                        "code": "REPORT_PROCESSING",
                        "retryable": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

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


class ShareLinkCreateView(APIView):
    """POST /api/v1/reports/sessions/{session_id}/share-link

    유효한 공유 토큰이 있으면 재사용, 없으면 신규 발급.
    응답: { share_url, expires_at, created }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = InterviewSession.objects.get(id=session_id, user=request.user)
        except InterviewSession.DoesNotExist:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

        report = _get_existing_report(session)
        if not report:
            return Response(
                {"detail": "리포트가 아직 생성되지 않았습니다.", "code": "REPORT_NOT_FOUND"},
                status=status.HTTP_404_NOT_FOUND,
            )

        token_obj, created = ReportShareToken.get_or_create_for_report(report, request.user)
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
        share_url = f"{frontend_base}/shared/{token_obj.token}"

        return Response(
            {
                "share_url": share_url,
                "expires_at": token_obj.expires_at.isoformat(),
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SharedReportView(APIView):
    """GET /api/v1/reports/share/{token}/

    인증 불필요. 토큰 유효성(존재 + 미만료) 검증 후 FinalReport summary 반환.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            token_obj = ReportShareToken.objects.select_related("report").get(token=token)
        except (ReportShareToken.DoesNotExist, ValueError):
            return Response({"detail": "유효하지 않은 공유 링크입니다."}, status=status.HTTP_404_NOT_FOUND)

        if not token_obj.is_valid:
            return Response(
                {"detail": "공유 링크가 만료되었습니다.", "code": "SHARE_LINK_EXPIRED"},
                status=status.HTTP_410_GONE,
            )

        report = token_obj.report
        return Response(
            {
                "report_id": str(report.id),
                "session_id": str(report.session_id),
                "generated_at": report.generated_at.isoformat(),
                # 공유 링크는 안전 필드만 노출한다(#4).
                "summary": build_shared_summary(report.summary),
                "expires_at": token_obj.expires_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )
