from django.urls import path
from .views import (
    AnalysisStartView,
    AnalysisStatusView,
    AnalysisMatchView,
    AnalysisQuestionsView,
    QuestionFeedbackView,
    JDSelectListView,
    ResumeSelectListView,
    CoverLetterSelectListView,
    JDCreateView,
    ResumeCreateView,
    CoverLetterCreateView,
    TalentCatalogView,
    JDTalentProfileView,
)

urlpatterns = [
    path("analyze/",              AnalysisStartView.as_view(),         name="analysis-analyze"),
    path("status/",               AnalysisStatusView.as_view(),        name="analysis-status"),
    path("match/",                AnalysisMatchView.as_view(),         name="analysis-match"),
    path("questions/",            AnalysisQuestionsView.as_view(),     name="analysis-questions"),
    path("feedback/",             QuestionFeedbackView.as_view(),      name="analysis-feedback"),
    # 선택용 목록
    path("select/jds/",           JDSelectListView.as_view(),          name="analysis-select-jds"),
    path("select/resumes/",       ResumeSelectListView.as_view(),      name="analysis-select-resumes"),
    path("select/cover-letters/", CoverLetterSelectListView.as_view(), name="analysis-select-cover-letters"),
    # 생성
    path("create/jds/",           JDCreateView.as_view(),              name="analysis-create-jd"),
    path("create/resumes/",       ResumeCreateView.as_view(),          name="analysis-create-resume"),
    path("create/cover-letters/", CoverLetterCreateView.as_view(),     name="analysis-create-cover-letter"),
    # 인재상
    path("talent-profiles/catalog/",          TalentCatalogView.as_view(),      name="talent-catalog"),
    path("jds/<uuid:jd_id>/talent-profile/",  JDTalentProfileView.as_view(),    name="jd-talent-profile"),
]
