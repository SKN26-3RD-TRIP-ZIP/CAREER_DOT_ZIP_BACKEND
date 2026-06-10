from django.urls import path
from .views import (
    SignupView,
    LoginView,
    CookieTokenRefreshView,
    VerifyEmailView,
    LogoutView,
)

urlpatterns = [
    path('signup', SignupView.as_view(), name='signup'),
    path('login', LoginView.as_view(), name='login'),
    path('verify-email', VerifyEmailView.as_view(), name='verify-email'),
    path('logout', LogoutView.as_view(), name='logout'),
    path('token/refresh', CookieTokenRefreshView.as_view(), name='token_refresh'),
]
