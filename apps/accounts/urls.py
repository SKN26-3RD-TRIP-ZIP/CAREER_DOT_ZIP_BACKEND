from django.urls import path

from .views import (
    SignupView,
    LoginView,
    CookieTokenRefreshView,
    VerifyEmailView,
    LogoutView,
    ResendVerificationView,
    CheckEmailView,
)
from .views_me import MeView
from .views_oauth import (
    OAuthCallbackView,
    OAuthExchangeView,
    OAuthSocialTermsView,
    OAuthStartView,
)
from .views_terms import MarketingConsentView, MyTermsAgreementListView

urlpatterns = [
    # no-slash alias (프론트/명세 호환)
    path("check-email", CheckEmailView.as_view()),
    path("signup", SignupView.as_view()),
    path("login", LoginView.as_view()),
    path("verify-email/resend", ResendVerificationView.as_view()),
    path("verify-email", VerifyEmailView.as_view()),
    path("resend-verification", ResendVerificationView.as_view()),
    path("logout", LogoutView.as_view()),
    path("token/refresh", CookieTokenRefreshView.as_view()),
    path("me", MeView.as_view()),
    path("oauth/exchange", OAuthExchangeView.as_view(), name="oauth-exchange"),
    path("oauth/social/terms", OAuthSocialTermsView.as_view(), name="oauth-social-terms"),
    path("oauth/<str:provider>/start", OAuthStartView.as_view(), name="oauth-start"),
    path("oauth/<str:provider>/callback", OAuthCallbackView.as_view(), name="oauth-callback"),
    path("users/me/terms-agreements", MyTermsAgreementListView.as_view(), name="my-terms-agreements"),
    path("users/me/terms-agreements/marketing", MarketingConsentView.as_view(), name="my-marketing-consent"),

    # trailing-slash route
    path("check-email/", CheckEmailView.as_view(), name="check-email"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("verify-email/resend/", ResendVerificationView.as_view(), name="verify-email-resend"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("oauth/exchange/", OAuthExchangeView.as_view()),
    path("oauth/social/terms/", OAuthSocialTermsView.as_view()),
    path("oauth/<str:provider>/start/", OAuthStartView.as_view()),
    path("oauth/<str:provider>/callback/", OAuthCallbackView.as_view()),
    path("users/me/terms-agreements/", MyTermsAgreementListView.as_view()),
    path("users/me/terms-agreements/marketing/", MarketingConsentView.as_view()),
]
