from django.urls import path

from .views import (
    SignupView,
    LoginView,
    CookieTokenRefreshView,
    VerifyEmailView,
    LogoutView,
)
from .views_me import MeView

urlpatterns = [
    # no-slash alias (프론트/명세 호환)
    path("signup", SignupView.as_view()),
    path("login", LoginView.as_view()),
    path("verify-email", VerifyEmailView.as_view()),
    path("logout", LogoutView.as_view()),
    path("token/refresh", CookieTokenRefreshView.as_view()),
    path("me", MeView.as_view()),

    # trailing-slash route
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
]
