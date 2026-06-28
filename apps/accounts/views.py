import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import update_last_login
from django.db import IntegrityError, transaction
from django.utils import timezone

from .serializers import SignupSerializer, LoginSerializer, SignupResponseSerializer
from .models import User, EmailVerificationCode, PendingRegistration
from .services.points import apply_point_policy
from .services.terms import record_signup_terms
from .codes import (
    issue_code,
    issue_pending_code,
    verify_code,
    verify_pending_code,
    VerifyResult,
    ResendCooldownError,
    invalidate_pending_code,
    pending_resend_retry_after,
    get_ttl_seconds,
    get_resend_cooldown_seconds,
)
from .emails import send_admin_signup_notification, send_verification_code_email

logger = logging.getLogger("apps.accounts")

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days
EMAIL_SEND_FAILED_RESPONSE = {
    "detail": "인증 메일 발송에 실패했습니다. 잠시 후 재전송해 주세요.",
    "code": "EMAIL_SEND_FAILED",
}


def _mask_email(email: str) -> str:
    local, sep, domain = (email or "").partition("@")
    if not sep:
        return "***"
    visible = local[:2] if len(local) >= 2 else local[:1]
    return f"{visible}***@{domain}"


def _verification_meta() -> dict:
    return {
        "expires_in": get_ttl_seconds(),
        "resend_after": get_resend_cooldown_seconds(),
    }


def _invalidate_active_codes(user) -> None:
    EmailVerificationCode.objects.filter(user=user, is_used=False).update(is_used=True)


def _email_send_failed_payload(email=None) -> dict:
    data = {
        "detail": "인증 메일 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        "code": "EMAIL_SEND_FAILED",
    }
    if email:
        data["email"] = email
    return data


def _pending_signup_payload(*, detail="인증번호를 발송했습니다.", retry_after=None) -> dict:
    data = {
        "detail": detail,
        **_verification_meta(),
    }
    if retry_after is not None:
        data["resend_after"] = retry_after
        data["retry_after"] = retry_after
    return data


class SignupView(APIView):
    """회원가입 엔드포인트. 성공 시 인증번호 메일과 관리자 알림 메일을 발송한다.

    인증번호 메일 발송 실패는 503으로 반환한다. 관리자 알림 실패는 가입 흐름을 막지 않는다.

    중복 이메일 정책:
    - banned 계정      → 403 (가입 차단)
    - is_verified=True → 409 "이미 가입된 이메일" (가입 차단)
    - is_verified=False→ 200 (가입 차단하지 않고 인증번호 재발급/재발송, requires_verification)
    이렇게 하여 인증 메일을 받지 못한 미인증 계정이 재가입 흐름에서 막히지 않도록 한다.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def _legacy_signup_post_unused(self, request):
        email = (request.data.get('email') or '').strip()

        # 1) 이미 존재하는 이메일 — 인증 완료/차단 계정만 가입을 막는다.
        existing_user = User.objects.filter(email=email).first() if email else None
        if existing_user is not None:
            if existing_user.status == 'banned':
                return Response(
                    {'error': 'This account has been banned. Please contact the administrator.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if existing_user.is_verified:
                return Response(
                    {'error': 'This email is already registered.'},
                    status=status.HTTP_409_CONFLICT,
                )
            # 미인증 기존 계정 — 차단 대신 인증번호 재발급/재발송 흐름으로 처리.
            return self._resend_for_unverified(existing_user)

        # 2) 신규 가입
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            try:
                code = issue_code(user)
                send_verification_code_email(user, code)
                logger.info(
                    "signup verification email sent user_id=%s email=%s",
                    user.id,
                    _mask_email(user.email),
                )
            except Exception as exc:  # noqa: BLE001
                _invalidate_active_codes(user)
                logger.warning(
                    "signup verification email failed user_id=%s email=%s exc=%s",
                    user.id,
                    _mask_email(user.email),
                    exc.__class__.__name__,
                )
                data = {
                    **EMAIL_SEND_FAILED_RESPONSE,
                    "requires_verification": True,
                    "email": user.email,
                }
                return Response(data, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            try:
                send_admin_signup_notification(user, signup_method="email")
            except Exception as exc:  # noqa: BLE001
                logger.warning("admin signup notification failed user_id=%s exc=%s", user.id, exc.__class__.__name__)

            response_serializer = SignupResponseSerializer(user)
            data = dict(response_serializer.data)
            data["requires_verification"] = True
            data["mail_sent"] = True
            data.update(_verification_meta())
            return Response(data, status=status.HTTP_201_CREATED)

        return Response(
            {'error': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @staticmethod
    def _resend_for_unverified(user):
        """미인증 기존 계정의 재가입 시도 — 새 인증번호 발급 후 재발송.

        - 쿨다운 미경과 시: 직전에 보낸 인증번호가 아직 유효하므로 재발송 없이 안내.
        - 발송 실패 시: 503 + EMAIL_SEND_FAILED 로 반환.
        """
        resent = False
        retry_after = None
        try:
            code = issue_code(user)
            send_verification_code_email(user, code)
            resent = True
            logger.info(
                "signup duplicate verification email sent user_id=%s email=%s",
                user.id,
                _mask_email(user.email),
            )
        except ResendCooldownError as exc:
            retry_after = exc.retry_after
            logger.info("signup resend skipped(cooldown) user_id=%s", user.id)
        except Exception as exc:  # noqa: BLE001
            _invalidate_active_codes(user)
            logger.warning(
                "signup duplicate verification email failed user_id=%s email=%s exc=%s",
                user.id,
                _mask_email(user.email),
                exc.__class__.__name__,
            )
            data = {
                **EMAIL_SEND_FAILED_RESPONSE,
                "requires_verification": True,
                "email": user.email,
            }
            return Response(data, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        data = {
            "email": user.email,
            "name": user.name,
            "requires_verification": True,
            "resent": resent,
            "mail_sent": resent,
        }
        data.update(_verification_meta())
        if retry_after is not None:
            data["resend_after"] = retry_after
            data["retry_after"] = retry_after
        if resent:
            data["message"] = "이미 가입 시도한 이메일입니다. 인증번호를 다시 보냈습니다."
        else:
            data["message"] = (
                "이미 가입 시도한 이메일입니다. 앞서 보낸 인증번호가 아직 유효합니다. "
                "메일함을 확인해주세요."
            )
        return Response(data, status=status.HTTP_200_OK)


    def post(self, request):
        data = request.data.copy()
        email = (data.get('email') or '').strip()
        if email:
            data['email'] = email

        existing_user = User.objects.filter(email=email).first() if email else None
        if existing_user is not None:
            if existing_user.status == 'banned':
                return Response(
                    {
                        'detail': 'This account has been banned. Please contact the administrator.',
                        'code': 'ACCOUNT_BANNED',
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if existing_user.is_verified:
                return Response(
                    {
                        'detail': 'This email is already registered.',
                        'code': 'EMAIL_ALREADY_REGISTERED',
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            return self._resend_for_unverified(existing_user)

        serializer = SignupSerializer(data=data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        attrs = serializer.validated_data
        now = timezone.now()
        password_hash = make_password(attrs['password'])
        pending = None
        code = None

        try:
            with transaction.atomic():
                pending = (
                    PendingRegistration.objects
                    .select_for_update()
                    .filter(email=attrs['email'])
                    .first()
                )
                if pending is None:
                    pending = PendingRegistration.objects.create(
                        email=attrs['email'],
                        password_hash=password_hash,
                        name=attrs['name'],
                        expires_at=now,
                        resend_available_at=now,
                        max_attempts=getattr(settings, "EMAIL_CODE_MAX_ATTEMPTS", 5),
                        terms_version=attrs.get('terms_version') or 'v1',
                        privacy_version=attrs.get('privacy_version') or 'v1',
                        terms_agreed=attrs['terms_agreed'],
                        privacy_agreed=attrs['privacy_agreed'],
                        marketing_agreed=attrs.get('marketing_agreed', False),
                        agreed_at=now,
                    )
                else:
                    retry_after = pending_resend_retry_after(pending, now=now)
                    pending.password_hash = password_hash
                    pending.name = attrs['name']
                    pending.terms_version = attrs.get('terms_version') or 'v1'
                    pending.privacy_version = attrs.get('privacy_version') or 'v1'
                    pending.terms_agreed = attrs['terms_agreed']
                    pending.privacy_agreed = attrs['privacy_agreed']
                    pending.marketing_agreed = attrs.get('marketing_agreed', False)
                    pending.agreed_at = now
                    pending.is_used = False
                    pending.verified_at = None
                    pending.save(
                        update_fields=[
                            'password_hash',
                            'name',
                            'terms_version',
                            'privacy_version',
                            'terms_agreed',
                            'privacy_agreed',
                            'marketing_agreed',
                            'agreed_at',
                            'is_used',
                            'verified_at',
                            'updated_at',
                        ]
                    )
                    if retry_after > 0:
                        return Response(
                            _pending_signup_payload(
                                detail='이미 인증 대기 중인 이메일입니다. 앞서 보낸 인증번호를 확인해 주세요.',
                                retry_after=retry_after,
                            ),
                            status=status.HTTP_200_OK,
                        )

                code = issue_pending_code(pending)
        except IntegrityError:
            return Response(
                {
                    'detail': 'This email already has a pending registration.',
                    'code': 'PENDING_REGISTRATION_EXISTS',
                    **_verification_meta(),
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            send_verification_code_email(pending, code)
            logger.info(
                "pending signup verification email sent pending_id=%s email=%s",
                pending.id,
                _mask_email(pending.email),
            )
        except Exception as exc:  # noqa: BLE001
            invalidate_pending_code(pending)
            logger.warning(
                "pending signup verification email failed pending_id=%s email=%s exc=%s",
                pending.id,
                _mask_email(pending.email),
                exc.__class__.__name__,
            )
            return Response(_email_send_failed_payload(pending.email), status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(_pending_signup_payload(), status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    """이메일 인증(6자리 인증번호). POST /api/v1/auth/verify-email  body: {"email","code"}"""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def _legacy_verify_post_unused(self, request):
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
                {'detail': '인증번호가 올바르지 않습니다.', 'code': 'VERIFY_CODE_INVALID'},
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
                {
                    'detail': '인증 시도 횟수를 초과했습니다. 인증번호를 재발송해 주세요.',
                    'code': 'VERIFY_TOO_MANY_ATTEMPTS',
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if result == VerifyResult.EXPIRED:
            return Response(
                {
                    'detail': '인증번호가 만료되었거나 존재하지 않습니다. 재발송해 주세요.',
                    'code': 'VERIFY_CODE_EXPIRED',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'detail': '인증번호가 올바르지 않습니다.', 'code': 'VERIFY_CODE_INVALID'},
            status=status.HTTP_400_BAD_REQUEST,
        )


    def post(self, request):
        email = (request.data.get('email') or '').strip()
        code = (request.data.get('code') or '').strip()
        if not email or not code:
            return Response(
                {'detail': '이메일과 인증번호를 모두 입력해 주세요.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pending = PendingRegistration.objects.filter(email=email).first()
        if pending is not None:
            return self._verify_pending(email=email, code=code, request=request)

        return self._verify_legacy(email=email, code=code)

    def _verify_pending(self, *, email, code, request=None):
        user = None
        try:
            with transaction.atomic():
                pending = PendingRegistration.objects.select_for_update().get(email=email)
                if pending.is_used:
                    return Response(
                        {
                            'detail': '이미 인증이 완료된 가입 요청입니다.',
                            'code': 'REGISTRATION_ALREADY_VERIFIED',
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                result = verify_pending_code(pending, code)
                if result == VerifyResult.OK:
                    if User.objects.filter(email=pending.email).exists():
                        return Response(
                            {
                                'detail': 'This email is already registered.',
                                'code': 'EMAIL_ALREADY_REGISTERED',
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    user = User.objects.create_user_with_password_hash(
                        email=pending.email,
                        password_hash=pending.password_hash,
                        name=pending.name,
                        is_verified=True,
                    )
                    record_signup_terms(user, pending, request=request)
                    try:
                        apply_point_policy(
                            user=user,
                            reason_code="AUTH.EMAIL_VERIFIED",
                            reference_id=str(user.id),
                            idempotency_key=f"AUTH.EMAIL_VERIFIED:{user.id}",
                            description="email verification reward",
                        )
                    except ValueError:
                        logger.info("email verification reward skipped user_id=%s", user.id)
                elif result == VerifyResult.TOO_MANY:
                    return Response(
                        {
                            'detail': '인증 시도 횟수를 초과했습니다. 인증번호를 재발송해 주세요.',
                            'code': 'VERIFY_TOO_MANY_ATTEMPTS',
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                elif result == VerifyResult.EXPIRED:
                    return Response(
                        {
                            'detail': '인증번호가 만료되었거나 존재하지 않습니다. 재발송해 주세요.',
                            'code': 'VERIFY_CODE_EXPIRED',
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        {'detail': '인증번호가 올바르지 않습니다.', 'code': 'VERIFY_CODE_INVALID'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        except PendingRegistration.DoesNotExist:
            return Response(
                {
                    'detail': '인증 대기 중인 가입 요청을 찾을 수 없습니다.',
                    'code': 'PENDING_REGISTRATION_NOT_FOUND',
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except IntegrityError:
            return Response(
                {
                    'detail': 'This email is already registered.',
                    'code': 'EMAIL_ALREADY_REGISTERED',
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            send_admin_signup_notification(user, signup_method="email")
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin signup notification failed user_id=%s exc=%s", user.id, exc.__class__.__name__)

        logger.info("email verified pending_id=%s user_id=%s", pending.id, user.id)
        return Response({'message': '이메일 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)

    def _verify_legacy(self, *, email, code):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {
                    'detail': '인증 대기 중인 가입 요청을 찾을 수 없습니다.',
                    'code': 'PENDING_REGISTRATION_NOT_FOUND',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_verified:
            return Response({'message': '이미 인증된 계정입니다.'}, status=status.HTTP_200_OK)

        result = verify_code(user, code)
        if result == VerifyResult.OK:
            user.is_verified = True
            user.save(update_fields=['is_verified', 'updated_at'])
            try:
                apply_point_policy(
                    user=user,
                    reason_code="AUTH.EMAIL_VERIFIED",
                    reference_id=str(user.id),
                    idempotency_key=f"AUTH.EMAIL_VERIFIED:{user.id}",
                    description="legacy email verification reward",
                )
            except ValueError:
                logger.info("legacy email verification reward skipped user_id=%s", user.id)
            logger.info("email verified(code legacy) user_id=%s", user.id)
            return Response({'message': '이메일 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)
        if result == VerifyResult.TOO_MANY:
            return Response(
                {
                    'detail': '인증 시도 횟수를 초과했습니다. 인증번호를 재발송해 주세요.',
                    'code': 'VERIFY_TOO_MANY_ATTEMPTS',
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if result == VerifyResult.EXPIRED:
            return Response(
                {
                    'detail': '인증번호가 만료되었거나 존재하지 않습니다. 재발송해 주세요.',
                    'code': 'VERIFY_CODE_EXPIRED',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'detail': '인증번호가 올바르지 않습니다.', 'code': 'VERIFY_CODE_INVALID'},
            status=status.HTTP_400_BAD_REQUEST,
        )


class ResendVerificationView(APIView):
    """
    이메일 인증 재발송. POST /api/v1/auth/resend-verification  body: {"email": "..."}

    - 이메일 열거(enumeration) 방지를 위해 가입/미가입 여부와 무관하게 항상 동일한 200 메시지를 반환한다.
    - 실제 발송은 '가입되어 있고 아직 미인증' 인 경우에만 수행한다.
    - 메일 발송 실패는 503 으로 반환한다. 토큰/인증번호는 로그에 미기록.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    GENERIC_MESSAGE = "입력하신 이메일이 가입되어 있고 아직 인증 전이라면, 인증번호를 다시 발송했습니다."

    def _legacy_resend_post_unused(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': self.GENERIC_MESSAGE, 'message': self.GENERIC_MESSAGE}, status=status.HTTP_200_OK)

        if user.is_verified:
            # 이미 인증된 계정 — 메일 재발송 없이 동일 메시지(열거 방지)
            return Response({'detail': self.GENERIC_MESSAGE, 'message': self.GENERIC_MESSAGE}, status=status.HTTP_200_OK)

        try:
            code = issue_code(user)
            send_verification_code_email(user, code)
            logger.info(
                "verification code resend sent user_id=%s email=%s",
                user.id,
                _mask_email(user.email),
            )
        except ResendCooldownError as exc:
            return Response(
                {
                    'detail': '잠시 후 다시 시도해 주세요.',
                    'code': 'RESEND_COOLDOWN',
                    'retry_after': exc.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception as exc:  # noqa: BLE001
            _invalidate_active_codes(user)
            logger.warning(
                "verification code resend failed user_id=%s email=%s exc=%s",
                user.id,
                _mask_email(user.email),
                exc.__class__.__name__,
            )
            return Response(EMAIL_SEND_FAILED_RESPONSE, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            {
                'detail': '인증번호를 다시 발송했습니다.',
                'message': '인증번호를 다시 발송했습니다.',
                **_verification_meta(),
            },
            status=status.HTTP_200_OK,
        )


    def post(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        pending = PendingRegistration.objects.filter(email=email).first()
        if pending is not None:
            return self._resend_pending(email)

        return self._resend_legacy(email)

    def _resend_pending(self, email):
        try:
            with transaction.atomic():
                pending = PendingRegistration.objects.select_for_update().get(email=email)
                if pending.is_used:
                    return Response(
                        {
                            'detail': '이미 인증이 완료된 가입 요청입니다.',
                            'code': 'REGISTRATION_ALREADY_VERIFIED',
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                code = issue_pending_code(pending)
        except PendingRegistration.DoesNotExist:
            return Response(
                {
                    'detail': '인증 대기 중인 가입 요청을 찾을 수 없습니다.',
                    'code': 'PENDING_REGISTRATION_NOT_FOUND',
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except ResendCooldownError as exc:
            return Response(
                {
                    'detail': '잠시 후 다시 시도해 주세요.',
                    'code': 'RESEND_COOLDOWN',
                    'retry_after': exc.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            send_verification_code_email(pending, code)
            logger.info(
                "pending verification code resend sent pending_id=%s email=%s",
                pending.id,
                _mask_email(pending.email),
            )
        except Exception as exc:  # noqa: BLE001
            invalidate_pending_code(pending)
            logger.warning(
                "pending verification code resend failed pending_id=%s email=%s exc=%s",
                pending.id,
                _mask_email(pending.email),
                exc.__class__.__name__,
            )
            return Response(_email_send_failed_payload(), status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            {
                'detail': '인증번호를 다시 발송했습니다.',
                'message': '인증번호를 다시 발송했습니다.',
                **_verification_meta(),
            },
            status=status.HTTP_200_OK,
        )

    def _resend_legacy(self, email):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {
                    'detail': '인증 대기 중인 가입 요청을 찾을 수 없습니다.',
                    'code': 'PENDING_REGISTRATION_NOT_FOUND',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_verified:
            return Response(
                {
                    'detail': '이미 인증된 계정입니다.',
                    'code': 'REGISTRATION_ALREADY_VERIFIED',
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            code = issue_code(user)
            send_verification_code_email(user, code)
            logger.info(
                "verification code resend sent user_id=%s email=%s",
                user.id,
                _mask_email(user.email),
            )
        except ResendCooldownError as exc:
            return Response(
                {
                    'detail': '잠시 후 다시 시도해 주세요.',
                    'code': 'RESEND_COOLDOWN',
                    'retry_after': exc.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception as exc:  # noqa: BLE001
            _invalidate_active_codes(user)
            logger.warning(
                "verification code resend failed user_id=%s email=%s exc=%s",
                user.id,
                _mask_email(user.email),
                exc.__class__.__name__,
            )
            return Response(_email_send_failed_payload(), status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            {
                'detail': '인증번호를 다시 발송했습니다.',
                'message': '인증번호를 다시 발송했습니다.',
                **_verification_meta(),
            },
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    """로그인. 인증된 계정에 access token + refresh cookie 발급."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # 로그인 요청엔 JWT 인증 제외 (만료 토큰으로 인한 401 방지)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']
            update_last_login(None, user)
            was_dormant = user.status == "dormant"
            update_fields = []
            if was_dormant:
                user.status = "active"
                update_fields.append("status")
            if user.dormancy_warning_sent_at is not None:
                user.dormancy_warning_sent_at = None
                update_fields.append("dormancy_warning_sent_at")
            if update_fields:
                update_fields.append("updated_at")
                user.save(update_fields=update_fields)
            today = timezone.localdate().isoformat()
            try:
                apply_point_policy(
                    user=user,
                    reason_code="LOGIN.DAILY",
                    reference_id=today,
                    idempotency_key=f"LOGIN.DAILY:{user.id}:{today}",
                    description="daily first login reward",
                )
            except ValueError:
                logger.info("daily login reward skipped user_id=%s", user.id)
            if was_dormant:
                try:
                    apply_point_policy(
                        user=user,
                        reason_code="DORMANT.RETURN_LOGIN",
                        reference_id=str(user.id),
                        idempotency_key=f"DORMANT.RETURN_LOGIN:{user.id}",
                        description="dormant account return reward",
                    )
                except ValueError:
                    logger.info("dormant return reward skipped user_id=%s", user.id)
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
                # 로컬은 False/Lax, 운영(HTTPS)은 .env 로 REFRESH_COOKIE_SECURE=True 주입.
                secure=getattr(settings, "REFRESH_COOKIE_SECURE", False),
                samesite=getattr(settings, "REFRESH_COOKIE_SAMESITE", "Lax"),
                path=getattr(settings, "REFRESH_COOKIE_PATH", "/"),
                domain=getattr(settings, "REFRESH_COOKIE_DOMAIN", None),
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
        if 'Account is withdrawn' in errors:
            return Response({'error': 'Account is withdrawn.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)


class CookieTokenRefreshView(APIView):
    """HttpOnly cookie 의 refresh token 으로 access token 재발급."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response({'error': 'Refresh token not found.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            serializer = TokenRefreshSerializer(data={'refresh': refresh_token})
            if serializer.is_valid():
                response = Response(
                    {'access_token': serializer.validated_data['access']},
                    status=status.HTTP_200_OK,
                )
                rotated_refresh = serializer.validated_data.get('refresh')
                if rotated_refresh:
                    response.set_cookie(
                        key=REFRESH_COOKIE_NAME,
                        value=rotated_refresh,
                        httponly=True,
                        secure=getattr(settings, "REFRESH_COOKIE_SECURE", False),
                        samesite=getattr(settings, "REFRESH_COOKIE_SAMESITE", "Lax"),
                        path=getattr(settings, "REFRESH_COOKIE_PATH", "/"),
                        domain=getattr(settings, "REFRESH_COOKIE_DOMAIN", None),
                        max_age=REFRESH_COOKIE_MAX_AGE,
                    )
                return response
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
        # 삭제 쿠키의 samesite 는 설정 시점과 동일해야 브라우저가 정확히 제거한다.
        response.delete_cookie(
            REFRESH_COOKIE_NAME,
            samesite=getattr(settings, "REFRESH_COOKIE_SAMESITE", "Lax"),
            path=getattr(settings, "REFRESH_COOKIE_PATH", "/"),
            domain=getattr(settings, "REFRESH_COOKIE_DOMAIN", None),
        )
        # 참고: simplejwt token_blacklist 앱 미설치 → 서버측 blacklist 미적용.
        # 서버측 폐기 필요 시 INSTALLED_APPS 에 token_blacklist 추가 + migration 선행
        # (DB 변경 → ERD/마이그레이션: NEEDS_CONFIRMATION).
        return response
