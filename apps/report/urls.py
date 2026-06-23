from django.urls import path
from .views import (
    FinalReportGenerateView,
    FinalReportDetailView,
    FinalReportListView,
    LatestSessionReportView,
    SessionFinalReportView,
    SessionFeedbackView,
    SessionRoadmapView,
    WeaknessRecommendedQuestionsView,
    TagRecommendedQuestionsView,
    ReportPDFDownloadView,
    ShareLinkCreateView,
    SharedReportView,
)

urlpatterns = [
    path("sessions/latest/report", LatestSessionReportView.as_view(), name="latest-session-report"),
    path("sessions/<uuid:session_id>/report", SessionFinalReportView.as_view(), name="session-final-report"),
    path("sessions/<uuid:session_id>/feedback", SessionFeedbackView.as_view(), name="session-feedback"),
    path("sessions/<uuid:session_id>/roadmap", SessionRoadmapView.as_view(), name="session-roadmap"),
    path("reports/sessions/<uuid:session_id>/generate", FinalReportGenerateView.as_view(), name="final-report-generate"),
    path("reports/sessions/<uuid:session_id>/share-link", ShareLinkCreateView.as_view(), name="report-share-link"),
    path("reports/sessions/<uuid:session_id>/recommendations", WeaknessRecommendedQuestionsView.as_view(), name="weakness-recommendations"),
    path("reports/sessions/<uuid:session_id>/pdf", ReportPDFDownloadView.as_view(), name="report-pdf-download"),
    path("reports/sessions/<uuid:session_id>", FinalReportDetailView.as_view(), name="final-report-detail"),
    path("reports/share/<uuid:token>/", SharedReportView.as_view(), name="report-shared-view"),
    path("reports/recommendations/by-tags", TagRecommendedQuestionsView.as_view(), name="tag-recommendations"),
    path("reports", FinalReportListView.as_view(), name="final-report-list"),
]
