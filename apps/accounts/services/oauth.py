from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import SocialAccount, User


OAUTH_STATE_SALT = 'accounts.oauth.state'
OAUTH_STATE_MAX_AGE = 10 * 60


class OAuthError(ValueError):
    code = 'OAUTH_ERROR'


class OAuthProviderNotConfigured(OAuthError):
    code = 'OAUTH_PROVIDER_NOT_CONFIGURED'


class OAuthStateInvalid(OAuthError):
    code = 'OAUTH_STATE_INVALID'


class OAuthAccountBlocked(OAuthError):
    code = 'OAUTH_ACCOUNT_BLOCKED'


class OAuthEmailRequired(OAuthError):
    code = 'OAUTH_EMAIL_REQUIRED'


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


def build_authorization_url(provider: str, *, next_path: str = '/') -> dict:
    config = get_provider_config(provider)
    if not config.is_configured:
        raise OAuthProviderNotConfigured('OAuth provider credentials are not configured.')

    nonce = secrets.token_urlsafe(24)
    state = signing.dumps(
        {
            'provider': config.provider,
            'nonce': nonce,
            'next_path': next_path or '/',
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
        'next_path': next_path or '/',
    }


def validate_oauth_state(provider: str, state: str) -> dict:
    try:
        payload = signing.loads(state, salt=OAUTH_STATE_SALT, max_age=OAUTH_STATE_MAX_AGE)
    except signing.BadSignature as exc:
        raise OAuthStateInvalid('OAuth state is invalid or expired.') from exc
    if payload.get('provider') != (provider or '').strip().lower():
        raise OAuthStateInvalid('OAuth state provider mismatch.')
    return payload


def exchange_code_for_profile(provider: str, *, code: str) -> dict:
    config = get_provider_config(provider)
    if not config.is_configured:
        raise OAuthProviderNotConfigured('OAuth provider credentials are not configured.')

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
    token_json = token_response.json()
    access_token = token_json.get('access_token')
    if not access_token:
        raise OAuthError('OAuth provider did not return an access token.')

    profile_response = requests.get(
        config.userinfo_url,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    profile_response.raise_for_status()
    raw_profile = profile_response.json()
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

        user = User.objects.select_for_update().filter(email=provider_email).first()
        created_user = False
        if user is None:
            user = User.objects.create(
                email=provider_email,
                name=name[:255],
                password=make_password(None),
                is_verified=True,
                status='active',
            )
            created_user = True
        elif user.status in {'withdrawn', 'banned'} or not user.is_active:
            raise OAuthAccountBlocked('This account cannot sign in with OAuth.')
        elif not user.is_verified:
            user.is_verified = True
            user.save(update_fields=['is_verified', 'updated_at'])

        social = SocialAccount.objects.create(
            user=user,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            last_login_at=now,
        )
        return user, social, created_user
