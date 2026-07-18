from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import SocialAccount, User


OAUTH_STATE_SALT = 'accounts.oauth.state'
OAUTH_STATE_MAX_AGE = 10 * 60

# 일회용 교환 코드(서명 토큰) 설정. 토큰 본문에는 user/jwt 가 들어가지 않고,
# 캐시 key(jti)만 들어간다. 실제 사용자 정보는 서버측 캐시에만 보관한다.
OAUTH_EXCHANGE_SALT = 'accounts.oauth.exchange'
OAUTH_EXCHANGE_CACHE_PREFIX = 'oauth:exchange:'

# 회원가입 또는 로그인 후 필수 약관 미동의 시 이동할 공통 프론트 경로.
TERMS_PATH = '/signup/terms'
# Backward-compatible import for older callers. New code must use TERMS_PATH.
SOCIAL_TERMS_PATH = TERMS_PATH
DEFAULT_NEXT_PATH = '/mypage'


class OAuthError(ValueError):
    code = 'OAUTH_ERROR'


class OAuthProviderNotConfigured(OAuthError):
    code = 'OAUTH_PROVIDER_NOT_CONFIGURED'


class OAuthStateInvalid(OAuthError):
    code = 'OAUTH_STATE_INVALID'


class OAuthCallbackInvalid(OAuthError):
    code = 'OAUTH_CALLBACK_INVALID'


class OAuthProviderResponseError(OAuthError):
    """Provider(token/userinfo) 호출이 실패했거나 Provider 가 error 를 반환한 경우."""

    code = 'OAUTH_PROVIDER_ERROR'


class OAuthAccountBlocked(OAuthError):
    code = 'OAUTH_ACCOUNT_BLOCKED'


class OAuthAccountConflict(OAuthError):
    """동일 이메일의 기존(로컬/타 Provider) 계정이 있으나 자동 연결하지 않는다."""

    code = 'OAUTH_ACCOUNT_CONFLICT'


class OAuthEmailRequired(OAuthError):
    code = 'OAUTH_EMAIL_REQUIRED'


class OAuthExchangeCodeInvalid(OAuthError):
    code = 'OAUTH_EXCHANGE_CODE_INVALID'


class OAuthExchangeCodeExpired(OAuthError):
    code = 'OAUTH_EXCHANGE_CODE_EXPIRED'


class OAuthExchangeCodeUsed(OAuthError):
    code = 'OAUTH_EXCHANGE_CODE_USED'


def _exchange_ttl_seconds() -> int:
    return int(getattr(settings, 'OAUTH_EXCHANGE_CODE_TTL_SECONDS', 120))


def sanitize_next_path(next_path: str | None, default: str = DEFAULT_NEXT_PATH) -> str:
    """Open Redirect 방지: 허용된 내부 경로(단일 '/' 시작)만 통과시킨다.

    - 반드시 '/' 로 시작, '//'(protocol-relative)·역슬래시·scheme(':') 금지
    - 위반 시 안전한 기본 경로(default)로 대체
    """
    if not next_path or not isinstance(next_path, str):
        return default
    path = next_path.strip()
    if not path.startswith('/'):
        return default
    if path.startswith('//') or path.startswith('/\\'):
        return default
    if '\\' in path or '://' in path:
        return default
    return path


@dataclass(frozen=True)
class OAuthProviderConfig:
    provider: str
    client_id: str
    client_secret: str
    redirect_uri: str
    auth_url: str
    token_url: str
    userinfo_url: str
    scope: str

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    @property
    def required_env(self) -> list[str]:
        prefix = self.provider.upper()
        return [
            f'{prefix}_OAUTH_CLIENT_ID',
            f'{prefix}_OAUTH_CLIENT_SECRET',
            f'{prefix}_OAUTH_REDIRECT_URI',
        ]


def get_provider_config(provider: str) -> OAuthProviderConfig:
    normalized = (provider or '').strip().lower()
    if normalized == SocialAccount.PROVIDER_GOOGLE:
        return OAuthProviderConfig(
            provider=normalized,
            client_id=getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', ''),
            client_secret=getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', ''),
            redirect_uri=getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', ''),
            auth_url='https://accounts.google.com/o/oauth2/v2/auth',
            token_url='https://oauth2.googleapis.com/token',
            userinfo_url='https://openidconnect.googleapis.com/v1/userinfo',
            scope='openid email profile',
        )
    if normalized == SocialAccount.PROVIDER_KAKAO:
        return OAuthProviderConfig(
            provider=normalized,
            client_id=getattr(settings, 'KAKAO_OAUTH_CLIENT_ID', ''),
            client_secret=getattr(settings, 'KAKAO_OAUTH_CLIENT_SECRET', ''),
            redirect_uri=getattr(settings, 'KAKAO_OAUTH_REDIRECT_URI', ''),
            auth_url='https://kauth.kakao.com/oauth/authorize',
            token_url='https://kauth.kakao.com/oauth/token',
            userinfo_url='https://kapi.kakao.com/v2/user/me',
            scope='profile_nickname account_email',
        )
    raise OAuthError('Unsupported OAuth provider.')


def build_authorization_url(provider: str, *, next_path: str = DEFAULT_NEXT_PATH, flow: str | None = None) -> dict:
    config = get_provider_config(provider)
    if not config.is_configured:
        raise OAuthProviderNotConfigured('OAuth provider credentials are not configured.')

    safe_next = sanitize_next_path(next_path, DEFAULT_NEXT_PATH)
    nonce = secrets.token_urlsafe(24)
    state = signing.dumps(
        {
            'provider': config.provider,
            'nonce': nonce,
            'next_path': safe_next,
            'flow': flow if flow in {'login', 'signup'} else None,
            'issued_at': timezone.now().isoformat(),
        },
        salt=OAUTH_STATE_SALT,
    )
    query = {
        'client_id': config.client_id,
        'redirect_uri': config.redirect_uri,
        'response_type': 'code',
        'scope': config.scope,
        'state': state,
    }
    if config.provider == SocialAccount.PROVIDER_GOOGLE:
        query['access_type'] = 'offline'
        query['include_granted_scopes'] = 'true'
        query['prompt'] = 'select_account'
        query['nonce'] = nonce

    return {
        'provider': config.provider,
        'auth_url': f'{config.auth_url}?{urlencode(query)}',
        'state': state,
        'nonce': nonce,
        'next_path': safe_next,
    }


def validate_oauth_state(provider: str, state: str) -> dict:
    try:
        payload = signing.loads(state, salt=OAUTH_STATE_SALT, max_age=OAUTH_STATE_MAX_AGE)
    except signing.BadSignature as exc:
        raise OAuthStateInvalid('OAuth state is invalid or expired.') from exc
    if payload.get('provider') != (provider or '').strip().lower():
        raise OAuthStateInvalid('OAuth state provider mismatch.')
    return payload


def _response_json_object(response, *, response_name: str) -> dict:
    """Decode a provider response without exposing its sensitive body."""
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise OAuthProviderResponseError(
            f'OAuth provider returned an invalid {response_name} response.'
        ) from exc
    if not isinstance(payload, dict):
        raise OAuthProviderResponseError(
            f'OAuth provider returned an invalid {response_name} response.'
        )
    return payload


def exchange_code_for_profile(provider: str, *, code: str) -> dict:
    config = get_provider_config(provider)
    if not config.is_configured:
        raise OAuthProviderNotConfigured('OAuth provider credentials are not configured.')

    try:
        token_response = requests.post(
            config.token_url,
            data={
                'grant_type': 'authorization_code',
                'client_id': config.client_id,
                'client_secret': config.client_secret,
                'redirect_uri': config.redirect_uri,
                'code': code,
            },
            timeout=10,
        )
        token_response.raise_for_status()
        token_json = _response_json_object(token_response, response_name='token')
        access_token = token_json.get('access_token')
        if not access_token:
            raise OAuthProviderResponseError('OAuth provider did not return an access token.')

        profile_response = requests.get(
            config.userinfo_url,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        profile_response.raise_for_status()
        raw_profile = _response_json_object(profile_response, response_name='profile')
    except requests.RequestException as exc:
        # 네트워크/HTTP 오류는 Provider 오류로 일반화한다.
        # (원문 메시지/Provider 토큰을 사용자에게 노출하지 않는다.)
        raise OAuthProviderResponseError('OAuth provider request failed.') from exc
    return normalize_provider_profile(config.provider, raw_profile)


def normalize_provider_profile(provider: str, raw_profile: dict) -> dict:
    if provider == SocialAccount.PROVIDER_GOOGLE:
        return {
            'provider_user_id': str(raw_profile.get('sub') or ''),
            'email': raw_profile.get('email') or '',
            'email_verified': bool(raw_profile.get('email_verified')),
            'name': raw_profile.get('name') or raw_profile.get('email') or 'Google User',
        }
    if provider == SocialAccount.PROVIDER_KAKAO:
        account = raw_profile.get('kakao_account') or {}
        profile = account.get('profile') or {}
        return {
            'provider_user_id': str(raw_profile.get('id') or ''),
            'email': account.get('email') or '',
            'email_verified': bool(account.get('is_email_verified', False)),
            'name': profile.get('nickname') or account.get('email') or 'Kakao User',
        }
    raise OAuthError('Unsupported OAuth provider.')


def get_or_create_social_user(provider: str, profile: dict) -> tuple[User, SocialAccount, bool]:
    provider_user_id = (profile.get('provider_user_id') or '').strip()
    provider_email = (profile.get('email') or '').strip().lower()
    name = (profile.get('name') or provider_email or 'Social User').strip()
    if not provider_user_id:
        raise OAuthError('OAuth provider profile is missing a stable user id.')
    if not provider_email:
        raise OAuthEmailRequired('OAuth provider did not provide an email address.')

    now = timezone.now()
    with transaction.atomic():
        social = (
            SocialAccount.objects
            .select_for_update()
            .select_related('user')
            .filter(provider=provider, provider_user_id=provider_user_id)
            .first()
        )
        if social is not None:
            user = social.user
            if user.status in {'withdrawn', 'banned'} or not user.is_active:
                raise OAuthAccountBlocked('This account cannot sign in with OAuth.')
            social.provider_email = provider_email
            social.last_login_at = now
            social.save(update_fields=['provider_email', 'last_login_at', 'updated_at'])
            return user, social, False

        # 이 Provider 의 SocialAccount 가 없는 상태에서 동일 이메일의 기존 계정이 있으면
        # 보안 검토 없이 자동 연결하지 않는다(계정 탈취/하이재킹 방지). 명시적 충돌로 처리한다.
        existing = User.objects.filter(email=provider_email).first()
        if existing is not None:
            if existing.status in {'withdrawn', 'banned'} or not existing.is_active:
                raise OAuthAccountBlocked('This account cannot sign in with OAuth.')
            raise OAuthAccountConflict(
                'An account with this email already exists. '
                'Please sign in with your existing method first, then link social login.'
            )

        # 신규 사용자: User + SocialAccount 생성. 비밀번호는 직접 저장하지 않는다(usable password 없음).
        # Use the custom manager instead of QuerySet.create(). Production still
        # has a legacy, non-null `role` column and the manager supplies its
        # compatibility value while also creating an unusable password.
        user = User.objects.create_user(
            email=provider_email,
            name=name[:255],
            password=None,
            is_verified=True,
            status='active',
        )
        social = SocialAccount.objects.create(
            user=user,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            last_login_at=now,
        )
        return user, social, True


# ===== 일회용 교환 코드 (Backend → Frontend 안전 토큰 전달) =====
# Access/Refresh 토큰을 URL/로그/state 에 노출하지 않기 위해, 짧은 수명의 일회용
# 교환 코드만 Frontend 로 전달하고, 실제 토큰은 별도 exchange API 에서 발급한다.
#
# 저장소: Django 캐시 프레임워크(현재 LocMemCache 기본값). DB 모델/마이그레이션을
# 추가하지 않는다. 단일 사용 보장은 캐시 key 의 atomic delete 결과로 판정한다.
# (운영에서 다중 서버 사용 시 LocMemCache 는 프로세스 로컬이라 공유되지 않으므로
#  Redis 등 공유 캐시로 전환해야 한다 — 보고서에 한계 명시.)


def _exchange_cache_key(jti: str) -> str:
    return f'{OAUTH_EXCHANGE_CACHE_PREFIX}{jti}'


def issue_exchange_code(*, user_id: int, provider: str, next_path: str, created: bool, needs_terms: bool) -> str:
    """일회용 교환 코드(서명 토큰)를 발급한다. 토큰 본문에는 jti 만 담는다."""
    jti = secrets.token_urlsafe(24)
    ttl = _exchange_ttl_seconds()
    cache.set(
        _exchange_cache_key(jti),
        {
            'user_id': int(user_id),
            'provider': provider,
            'next_path': sanitize_next_path(next_path, DEFAULT_NEXT_PATH),
            'created': bool(created),
            'needs_terms': bool(needs_terms),
        },
        # 서명 만료가 먼저 트리거되도록 캐시 TTL 에 약간의 버퍼를 둔다.
        timeout=ttl + 30,
    )
    return signing.dumps({'jti': jti}, salt=OAUTH_EXCHANGE_SALT)


def consume_exchange_code(code: str) -> dict:
    """교환 코드를 1회만 소비한다. 만료/위조/재사용을 구분해 예외로 던진다."""
    if not code or not isinstance(code, str):
        raise OAuthExchangeCodeInvalid('Exchange code is required.')
    ttl = _exchange_ttl_seconds()
    try:
        payload = signing.loads(code, salt=OAUTH_EXCHANGE_SALT, max_age=ttl)
    except signing.SignatureExpired as exc:
        raise OAuthExchangeCodeExpired('Exchange code has expired.') from exc
    except signing.BadSignature as exc:
        raise OAuthExchangeCodeInvalid('Exchange code is invalid.') from exc

    jti = payload.get('jti')
    if not jti:
        raise OAuthExchangeCodeInvalid('Exchange code is malformed.')

    key = _exchange_cache_key(jti)
    data = cache.get(key)
    if data is None:
        # 서명은 유효/미만료인데 캐시에 없으면 이미 소비된 것으로 본다.
        raise OAuthExchangeCodeUsed('Exchange code has already been used.')
    # 단일 사용 보장: delete 가 True 를 반환한 요청만 성공(동시성 경합 시 1명만 통과).
    if not cache.delete(key):
        raise OAuthExchangeCodeUsed('Exchange code has already been used.')
    return data
