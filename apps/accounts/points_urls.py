from django.urls import path

from .views_points import InterviewSessionStartPointPolicyView, MyPointBalanceView, MyPointHistoryView
from .views_terms import MarketingConsentView, MyTermsAgreementListView


urlpatterns = [
    path("users/me/points", MyPointBalanceView.as_view(), name="my-point-balance"),
    path("users/me/points/history", MyPointHistoryView.as_view(), name="my-point-history"),
    path(
        "users/me/points/policies/interview-session-start",
        InterviewSessionStartPointPolicyView.as_view(),
        name="my-interview-session-start-point-policy",
    ),
    path("users/me/terms-agreements", MyTermsAgreementListView.as_view(), name="my-terms-agreements-root"),
    path("users/me/terms-agreements/marketing", MarketingConsentView.as_view(), name="my-marketing-consent-root"),
]
