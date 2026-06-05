from django.urls import path
from .views import AnalysisStartView, AnalysisStatusView, AnalysisResultView

urlpatterns = [
    path("start/",                   AnalysisStartView.as_view()),
    path("<int:session_id>/status/", AnalysisStatusView.as_view()),
    path("<int:session_id>/result/", AnalysisResultView.as_view()),
]
