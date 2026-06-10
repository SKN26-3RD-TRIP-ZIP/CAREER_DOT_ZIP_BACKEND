import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from django.core import signing

from .serializers import SignupSerializer, LoginSerializer, SignupResponseSerializer
from .models import User
from .tokens import verify_email_verification_token
from .emails import send_welcome_email, send_admin_signup_notification

logger = logging.getLogger("apps.accounts")

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days


class SignupView(APIView):
    """회원가입 엔드포인트. 성공 시 환영/관리자 알림 메일을 발송(실패해도 가입은 성공)."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            mail_failed = False
            try:
                send_welcome_email(user)
            except Exception:  # noqa: BLE001
                mail_failed = True
                logger.exception("welcome email 발송 실패 user_id=%s", user.id)
            try:
                send_admin_signup_notification(user, signup_method="email")
            except Exception:  # noqa: BLE001
                logger.exception("admin signup 알림 발송 실패 user_id=%s", user.id)

            response_serializer = SignupResponseSerializer(user)
            data = dict(response_serializer.data)
            if mail_failed:
                data["message"] = (
                    "가입이 완료되었습니다. 인증 메일 발송이 지연될 수 있습니다. "
                    "메일이 오지 않으면 잠시 후 다시 시도해주세요."
                )
            return Response(data, status=status.HTTP_201_CREATED)

        if 'email' in serializer.errors:
            return Response(
                {'error': 'This email is already registered.'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {'error': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class VerifyEmailView(APIView):
    """이메일 인증. GET /api/v1/auth/verify-email?token=..."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = request.query_params.get('token', '')
        invalid = Response(
            {'detail': '유효하지 않거나 만료된 인증 토큰입니다.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
        if not token:
            return invalid
        try:
            payload = verify_email_verification_token(token)
        except signing.SignatureExpired:
            return invalid
        except signing.BadSignature:
            return invalid

        try:
            user = User.objects.get(id=payload.get('uid'), email=payload.get('email'))
        except User.DoesNotExist:
            return invalid

        if user.is_verified:
            return Response({'message': '이미 인증된 계정입니다.'}, status=status.HTTP_200_OK)

        user.is_verified = True
        user.save(update_fields=['is_verified', 'updated_at'])
        logger.info("email verified user_id=%s", user.id)
        return Response({'message': '이메일 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)


class LoginView(APIView):
    """로그인. 인증된 계정에 access token + refresh cookie 발급."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)

            response = Response(
                {'access_token': access_token, 'token_type': 'Bearer'},
                status=status.HTTP_200_OK,
            )
            response.set_cookie(
                key=REFRESH_COOKIE_NAME,
                value=str(refresh),
                httponly=True,
                secure=False,  # 운영(prod)에서는 True 로 전환 필요
                samesite='Lax',
                max_age=REFRESH_COOKIE_MAX_AGE,
            )
            return response

        errors = str(serializer.errors)
        if 'Invalid email or password' in errors:
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)
        if 'Email not verified' in errors:
            return Response({'error': 'Email not verified.'}, status=status.HTTP_403_FORBIDDEN)
        if 'Account is suspended' in errors:
            return Response({'error': 'Account is suspended.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)


class CookieTokenRefreshView(APIView):
    """HttpOnly cookie 의 refresh token 으로 access token 재발급."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response({'error': 'Refresh token not found.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            serializer = TokenRefreshSerializer(data={'refresh': refresh_token})
            if serializer.is_valid():
                return Response(
                    {'access_token': serializer.validated_data['access']},
                    status=status.HTTP_200_OK,
                )
            return Response({'error': 'Invalid or expired refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)
        except (InvalidToken, TokenError):
            return Response({'error': 'Invalid or expired refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:  # noqa: BLE001
            return Response({'error': 'Token refresh failed.'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    """로그아웃. refresh cookie 삭제. (access token 은 클라이언트에서 폐기)"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        response = Response({'message': '로그아웃 완료'}, status=status.HTTP_200_OK)
        response.delete_cookie(REFRESH_COOKIE_NAME, samesite='Lax')
        # 참고: simplejwt token_blacklist 앱 미설치 → 서버측 blacklist 미적용.
        # 서버측 폐기 필요 시 INSTALLED_APPS 에 token_blacklist 추가 + migration 선행
        # (DB 변경 → ERD/마이그레이션: NEEDS_CONFIRMATION).
        return response
