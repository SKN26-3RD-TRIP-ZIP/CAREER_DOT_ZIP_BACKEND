from django.urls import path

from .views import (
    SignupView,
    LoginView,
    CookieTokenRefreshView,
    VerifyEmailView,
    LogoutView,
)

urlpatterns = [
    # 기존 API 명세/프론트 호환용 no-slash alias
    path("signup", SignupView.as_view()),
    path("login", LoginView.as_view()),
    path("verify-email", VerifyEmailView.as_view()),
    path("logout", LogoutView.as_view()),
    path("token/refresh", CookieTokenRefreshView.as_view()),

    # develop 기준 trailing-slash route
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
]
