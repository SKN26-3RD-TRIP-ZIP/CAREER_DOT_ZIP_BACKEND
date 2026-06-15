import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from django.contrib.auth.models import update_last_login

from .serializers import SignupSerializer, LoginSerializer, SignupResponseSerializer
from .models import User
from .codes import issue_code, verify_code, VerifyResult, ResendCooldownError
from .emails import send_admin_signup_notification, send_verification_code_email

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
                code = issue_code(user)
                send_verification_code_email(user, code)
            except Exception:  # noqa: BLE001
                mail_failed = True
                logger.exception("인증번호 메일 발송 실패 user_id=%s", user.id)
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
            email = request.data.get('email')
            existing_user = User.objects.filter(email=email).first()
            if existing_user and existing_user.status == 'banned':
                return Response(
                    {'error': 'This account has been banned. Please contact the administrator.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            if existing_user:
                return Response(
                    {'error': 'This email is already registered.'},
                    status=status.HTTP_409_CONFLICT,
                )

        return Response(
            {'error': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class VerifyEmailView(APIView):
    """이메일 인증(6자리 인증번호). POST /api/v1/auth/verify-email  body: {"email","code"}"""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        code = (request.data.get('code') or '').strip()
        if not email or not code:
            return Response(
                {'detail': '이메일과 인증번호를 모두 입력해 주세요.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # 열거 방지: 코드 불일치와 동일한 응답
            return Response(
                {'detail': '인증번호가 올바르지 않습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.is_verified:
            return Response({'message': '이미 인증된 계정입니다.'}, status=status.HTTP_200_OK)

        result = verify_code(user, code)
        if result == VerifyResult.OK:
            user.is_verified = True
            user.save(update_fields=['is_verified', 'updated_at'])
            logger.info("email verified(code) user_id=%s", user.id)
            return Response({'message': '이메일 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)
        if result == VerifyResult.TOO_MANY:
            return Response(
                {'detail': '인증 시도 횟수를 초과했습니다. 인증번호를 재발송해 주세요.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if result == VerifyResult.EXPIRED:
            return Response(
                {'detail': '인증번호가 만료되었거나 존재하지 않습니다. 재발송해 주세요.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'detail': '인증번호가 올바르지 않습니다.'},
            status=status.HTTP_400_BAD_REQUEST,
        )


class ResendVerificationView(APIView):
    """
    이메일 인증 재발송. POST /api/v1/auth/resend-verification  body: {"email": "..."}

    - 이메일 열거(enumeration) 방지를 위해 가입/미가입 여부와 무관하게 항상 동일한 200 메시지를 반환한다.
    - 실제 발송은 '가입되어 있고 아직 미인증' 인 경우에만 수행한다.
    - 메일 발송 실패가 요청 실패로 이어지지 않게 한다(로그만 남김, 토큰은 로그에 미기록).
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    GENERIC_MESSAGE = "입력하신 이메일이 가입되어 있고 아직 인증 전이라면, 인증 메일을 다시 보냈습니다."

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'message': self.GENERIC_MESSAGE}, status=status.HTTP_200_OK)

        if user.is_verified:
            # 이미 인증된 계정 — 메일 재발송 없이 동일 메시지(열거 방지)
            return Response({'message': self.GENERIC_MESSAGE}, status=status.HTTP_200_OK)

        try:
            code = issue_code(user)
            send_verification_code_email(user, code)
        except ResendCooldownError as exc:
            return Response(
                {'detail': f'잠시 후 다시 시도해 주세요. ({exc.retry_after}초 후 재발송 가능)'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception:  # noqa: BLE001
            logger.exception("verification code resend 실패 user_id=%s", user.id)

        return Response({'message': self.GENERIC_MESSAGE}, status=status.HTTP_200_OK)


class LoginView(APIView):
    """로그인. 인증된 계정에 access token + refresh cookie 발급."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # 로그인 요청엔 JWT 인증 제외 (만료 토큰으로 인한 401 방지)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']
            update_last_login(None, user)
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
        if 'Account is banned' in errors:
            return Response({'error': 'Account is banned.'}, status=status.HTTP_403_FORBIDDEN)
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
