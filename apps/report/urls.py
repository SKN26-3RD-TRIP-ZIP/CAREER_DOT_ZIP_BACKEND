from django.urls import path
from .views import (
    FinalReportGenerateView,
    FinalReportDetailView,
    FinalReportListView,
    LatestSessionReportView,
    SessionFinalReportView,
)

urlpatterns = [
    path('sessions/latest/report', LatestSessionReportView.as_view(), name='latest-session-report'),
    path('sessions/<uuid:session_id>/report', SessionFinalReportView.as_view(), name='session-final-report'),
    path('reports/sessions/<uuid:session_id>/generate', FinalReportGenerateView.as_view(), name='final-report-generate'),
    path('reports/sessions/<uuid:session_id>', FinalReportDetailView.as_view(), name='final-report-detail'),
    path('reports', FinalReportListView.as_view(), name='final-report-list'),
]
