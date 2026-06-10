from django.urls import path
from .views import (
    AnalysisStartView,
    AnalysisStatusView,
    AnalysisMatchView,
    JDSelectListView,
    ResumeSelectListView,
    CoverLetterSelectListView,
    JDCreateView,
    ResumeCreateView,
    CoverLetterCreateView,
)

urlpatterns = [
    path("analyze/",              AnalysisStartView.as_view(),         name="analysis-analyze"),
    path("status/",               AnalysisStatusView.as_view(),        name="analysis-status"),
    path("match/",                AnalysisMatchView.as_view(),         name="analysis-match"),
    # 선택용 목록
    path("select/jds/",           JDSelectListView.as_view(),          name="analysis-select-jds"),
    path("select/resumes/",       ResumeSelectListView.as_view(),      name="analysis-select-resumes"),
    path("select/cover-letters/", CoverLetterSelectListView.as_view(), name="analysis-select-cover-letters"),
    # 생성
    path("create/jds/",           JDCreateView.as_view(),              name="analysis-create-jd"),
    path("create/resumes/",       ResumeCreateView.as_view(),          name="analysis-create-resume"),
    path("create/cover-letters/", CoverLetterCreateView.as_view(),     name="analysis-create-cover-letter"),
]
