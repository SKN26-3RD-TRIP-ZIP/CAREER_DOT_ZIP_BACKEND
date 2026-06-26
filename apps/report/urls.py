from django.urls import path
from .views import (
    ActionPlanPatchView,
    FinalReportGenerateView,
    FinalReportDetailView,
    FinalReportListView,
    LatestSessionReportView,
    ReportActionPlanCreateView,
    SessionFinalReportView,
    SessionFeedbackView,
    WeaknessRecommendedQuestionsView,
    TagRecommendedQuestionsView,
    UserActionPlanListView,
    ReportPDFDownloadView,
)

urlpatterns = [
    path("sessions/latest/report", LatestSessionReportView.as_view(), name="latest-session-report"),
    path("sessions/<uuid:session_id>/report", SessionFinalReportView.as_view(), name="session-final-report"),
    path("sessions/<uuid:session_id>/feedback", SessionFeedbackView.as_view(), name="session-feedback"),
    path("reports/sessions/<uuid:session_id>/generate", FinalReportGenerateView.as_view(), name="final-report-generate"),
    path("reports/sessions/<uuid:session_id>/recommendations", WeaknessRecommendedQuestionsView.as_view(), name="weakness-recommendations"),
    path("reports/sessions/<uuid:session_id>/pdf", ReportPDFDownloadView.as_view(), name="report-pdf-download"),
    path("reports/sessions/<uuid:session_id>", FinalReportDetailView.as_view(), name="final-report-detail"),
    path("reports/<uuid:report_id>/action-plans", ReportActionPlanCreateView.as_view(), name="report-action-plan-create"),
    path("action-plans/<uuid:action_plan_id>", ActionPlanPatchView.as_view(), name="action-plan-patch"),
    path("users/me/action-plans", UserActionPlanListView.as_view(), name="user-action-plan-list"),
    path("reports/recommendations/by-tags", TagRecommendedQuestionsView.as_view(), name="tag-recommendations"),
    path("reports", FinalReportListView.as_view(), name="final-report-list"),
]
