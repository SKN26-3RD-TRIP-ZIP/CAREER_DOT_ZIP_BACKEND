import logging
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.emails import send_admin_signup_notification
from apps.accounts.models import User
from apps.accounts.services.oauth import (
    DEFAULT_NEXT_PATH,
    SOCIAL_TERMS_PATH,
    OAuthAccountBlocked,
    OAuthAccountConflict,
    OAuthCallbackInvalid,
    OAuthEmailRequired,
    OAuthError,
    OAuthExchangeCodeExpired,
    OAuthExchangeCodeInvalid,
    OAuthExchangeCodeUsed,
    OAuthProviderNotConfigured,
    OAuthProviderResponseError,
    OAuthStateInvalid,
    build_authorization_url,
    consume_exchange_code,
    exchange_code_for_profile,
    get_or_create_social_user,
    get_provider_config,
    issue_exchange_code,
    sanitize_next_path,
    validate_oauth_state,
)
from apps.accounts.services.login import complete_login
from apps.accounts.services.points import apply_point_policy
from apps.accounts.services.terms import record_social_signup_terms, required_terms_reconsent_status
from apps.accounts.views import REFRESH_COOKIE_MAX_AGE, REFRESH_COOKIE_NAME

logger = logging.getLogger("apps.accounts")


class OAuthStartQuerySerializer(serializers.Serializer):
    next = serializers.CharField(required=False, allow_blank=True, max_length=255)
    flow = serializers.ChoiceField(choices=['login', 'signup'], required=False, allow_blank=True)


class OAuthExchangeSerializer(serializers.Serializer):
    code = serializers.CharField()


class OAuthSocialTermsSerializer(serializers.Serializer):
    terms_agreed = serializers.BooleanField()
    privacy_agreed = serializers.BooleanField()
    marketing_agreed = serializers.BooleanField(required=False, default=False)


def _provider_not_configured_response(provider):
    """OAuth start 전용 응답(JSON). Frontend 가 '준비 중' 안내를 띄울 수 있게 한다."""
    config = get_provider_config(provider)
    return Response(
        {
            'detail': 'OAuth provider credentials are not configured.',
            'code': 'OAUTH_PROVIDER_NOT_CONFIGURED',
            'status': 'ENV_REQUIRED',
            'provider': config.provider,
            'required_env': config.required_env,
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _frontend_callback_url(*, code=None, error=None):
    """Frontend OAuth callback 절대 URL 생성. 토큰/오류상세/Provider 토큰은 절대 포함하지 않는다."""
    base = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')
    path = getattr(settings, 'FRONTEND_OAUTH_CALLBACK_PATH', '/oauth/callback')
    if not path.startswith('/'):
        path = '/' + path
    params = {}
    if code:
        params['code'] = code
    if error:
        params['error'] = error
    query = f'?{urlencode(params)}' if params else ''
    return f'{base}{path}{query}'


def _redirect_with_error(error_code: str):
    return HttpResponseRedirect(_frontend_callback_url(error=error_code))


def _redirect_with_code(code: str):
    return HttpResponseRedirect(_frontend_callback_url(code=code))


def _set_refresh_cookie(response, refresh):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=str(refresh),
        httponly=True,
        secure=getattr(settings, 'REFRESH_COOKIE_SECURE', False),
        samesite=getattr(settings, 'REFRESH_COOKIE_SAMESITE', 'Lax'),
        path=getattr(settings, 'REFRESH_COOKIE_PATH', '/'),
        domain=getattr(settings, 'REFRESH_COOKIE_DOMAIN', None),
        max_age=REFRESH_COOKIE_MAX_AGE,
    )


def _is_blocked(user) -> bool:
    return user.status in {'withdrawn', 'banned'} or not user.is_active


def _award_social_signup_rewards(user, provider):
    """신규 소셜 가입 1회 적립/메일. created=True 분기에서만 호출되므로 사용자당 1회.

    포인트는 idempotency_key 로 이중 적립을 방지한다(이메일 인증 보상과 동일 키 재사용).
    """
    try:
        reward = apply_point_policy(
            user=user,
            reason_code='AUTH.EMAIL_VERIFIED',
            reference_id=str(user.id),
            idempotency_key=f'AUTH.EMAIL_VERIFIED:{user.id}',
            description=f'{provider} social signup reward',
        )
    except ValueError:
        logger.info("social signup reward skipped user_id=%s provider=%s", user.id, provider)
        return
    if not reward.created:
        return
    try:
        send_admin_signup_notification(user, signup_method=provider)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "admin signup notification failed user_id=%s provider=%s exc=%s",
            user.id,
            provider,
            exc.__class__.__name__,
        )


class OAuthStartView(APIView):
    """OAuth 시작. provider 인가 URL/state 를 JSON 으로 반환한다(기존 계약 유지)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, provider):
        serializer = OAuthStartQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            data = build_authorization_url(
                provider,
                next_path=serializer.validated_data.get('next') or DEFAULT_NEXT_PATH,
                flow=serializer.validated_data.get('flow') or None,
            )
        except OAuthProviderNotConfigured:
            return _provider_not_configured_response(provider)
        except OAuthError as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data, status=status.HTTP_200_OK)


class OAuthCallbackView(APIView):
    """Provider redirect_uri 대상. 처리 후 항상 Frontend 로 302 Redirect 한다(JSON/JWT 비노출)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, provider):
        return self._handle(request, provider, request.query_params)

    def post(self, request, provider):
        return self._handle(request, provider, request.data)

    def _handle(self, request, provider, data):
        # 1) Provider 가 error 를 돌려준 경우(동의 취소 / KOE004 등 관리자 설정 문제 포함)
        provider_error = data.get('error')
        if provider_error:
            logger.info("oauth callback provider error provider=%s code=%s", provider, provider_error)
            return _redirect_with_error('OAUTH_PROVIDER_ERROR')

        code = data.get('code')
        state = data.get('state')
        if not code or not state:
            return _redirect_with_error('OAUTH_CALLBACK_INVALID')

        try:
            state_payload = validate_oauth_state(provider, state)
            profile = exchange_code_for_profile(provider, code=code)
            user, social, created = get_or_create_social_user(provider, profile)
        except OAuthProviderNotConfigured:
            return _redirect_with_error('OAUTH_PROVIDER_NOT_CONFIGURED')
        except OAuthStateInvalid:
            return _redirect_with_error('OAUTH_STATE_INVALID')
        except OAuthCallbackInvalid:
            return _redirect_with_error('OAUTH_CALLBACK_INVALID')
        except OAuthEmailRequired:
            return _redirect_with_error('OAUTH_EMAIL_REQUIRED')
        except OAuthAccountBlocked:
            return _redirect_with_error('OAUTH_ACCOUNT_BLOCKED')
        except OAuthAccountConflict:
            return _redirect_with_error('OAUTH_ACCOUNT_CONFLICT')
        except OAuthProviderResponseError:
            return _redirect_with_error('OAUTH_PROVIDER_ERROR')
        except OAuthError:
            # 알 수 없는 OAuth 오류도 Provider 오류로 일반화(상세/토큰 비노출)
            return _redirect_with_error('OAUTH_PROVIDER_ERROR')
        except Exception:  # noqa: BLE001
            # Do not log provider tokens or response bodies. The traceback is
            # enough to diagnose production-only failures without leaking secrets.
            logger.exception("oauth callback unexpected error provider=%s", provider)
            return _redirect_with_error('OAUTH_PROVIDER_ERROR')

        next_path = sanitize_next_path(state_payload.get('next_path'), DEFAULT_NEXT_PATH)
        needs_terms = bool(required_terms_reconsent_status(user))
        if needs_terms:
            next_path = SOCIAL_TERMS_PATH
        elif created:
            _award_social_signup_rewards(user, provider)

        logger.info(
            "oauth callback ok provider=%s user_id=%s created=%s needs_terms=%s",
            provider,
            user.id,
            created,
            needs_terms,
        )
        exchange_code = issue_exchange_code(
            user_id=user.id,
            provider=provider,
            next_path=next_path,
            created=created,
            needs_terms=needs_terms,
        )
        return _redirect_with_code(exchange_code)


class OAuthExchangeView(APIView):
    """일회용 교환 코드 → Career.zip access token + refresh 쿠키(기존 로그인과 동일 정책)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = OAuthExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = consume_exchange_code(serializer.validated_data['code'])
        except OAuthExchangeCodeExpired as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except OAuthExchangeCodeUsed as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_409_CONFLICT)
        except OAuthExchangeCodeInvalid as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(id=payload.get('user_id')).first()
        if user is None or _is_blocked(user):
            return Response(
                {'detail': 'This account cannot sign in with OAuth.', 'code': 'OAUTH_ACCOUNT_BLOCKED'},
                status=status.HTTP_403_FORBIDDEN,
            )

        complete_login(user, award_rewards=not bool(payload.get('needs_terms')))
        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                'access_token': str(refresh.access_token),
                'token_type': 'Bearer',
                'provider': payload.get('provider'),
                'created': bool(payload.get('created')),
                'needs_terms': bool(payload.get('needs_terms')),
                'next_path': sanitize_next_path(payload.get('next_path'), DEFAULT_NEXT_PATH),
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, refresh)
        return response


class OAuthSocialTermsView(APIView):
    """소셜 간편가입 필수 약관 동의 제출. 동의 완료 시 /mypage 로 이동 가능."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OAuthSocialTermsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not (data['terms_agreed'] and data['privacy_agreed']):
            return Response(
                {'detail': '필수 약관에 모두 동의해야 가입이 완료됩니다.', 'code': 'TERMS_REQUIRED'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record_social_signup_terms(
            user=request.user,
            terms_agreed=True,
            privacy_agreed=True,
            marketing_agreed=bool(data.get('marketing_agreed')),
            request=request,
        )
        complete_login(request.user)
        social = request.user.social_accounts.order_by('created_at', 'id').first()
        if social is not None:
            _award_social_signup_rewards(request.user, social.provider)
        return Response(
            {'detail': '약관 동의가 완료되었습니다.', 'next_path': DEFAULT_NEXT_PATH},
            status=status.HTTP_200_OK,
        )
