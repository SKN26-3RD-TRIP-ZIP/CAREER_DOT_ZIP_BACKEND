from django.urls import path
from .views import AnalysisStartView, AnalysisStatusView, AnalysisMatchView

urlpatterns = [
    path("analyze/",  AnalysisStartView.as_view(),  name="analysis-analyze"),
    path("status/",   AnalysisStatusView.as_view(), name="analysis-status"),
    path("match/",    AnalysisMatchView.as_view(),  name="analysis-match"),
]
