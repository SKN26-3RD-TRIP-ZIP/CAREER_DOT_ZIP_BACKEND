"""소셜 로그인/간편가입(OAuth) 흐름 테스트.

외부 Provider(Google/Kakao) 호출은 모두 Mock 처리하여 실제 네트워크 호출 없이 검증한다.
검증 포인트:
  - callback 은 JSON 이 아니라 Frontend 로 302 Redirect
  - access/refresh 토큰이 URL 에 포함되지 않음
  - 일회용 교환 코드: 단일 사용 / 만료 / 위조 구분
  - 기존 사용자 로그인 / 신규 가입 / 약관 미동의 redirect / 중복 생성 방지
  - 동일 이메일 충돌(자동 연결 금지) / state 위조·만료 / code·email 누락 / 차단 사용자
  - 허용되지 않은 next URL 차단(Open Redirect 방지)
"""
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import SocialAccount, TermsDocument, User
from apps.accounts.services import oauth as oauth_service
from apps.accounts.services.oauth import (
    OAuthExchangeCodeExpired,
    OAuthExchangeCodeInvalid,
    OAuthExchangeCodeUsed,
    build_authorization_url,
    consume_exchange_code,
    issue_exchange_code,
    sanitize_next_path,
)

FRONTEND_BASE_URL = 'http://localhost:5173'
FRONTEND_OAUTH_CALLBACK_PATH = '/oauth/callback'

OAUTH_SETTINGS = dict(
    GOOGLE_OAUTH_CLIENT_ID='google-client-id',
    GOOGLE_OAUTH_CLIENT_SECRET='google-client-secret',
    GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8000/api/v1/auth/oauth/google/callback',
    KAKAO_OAUTH_CLIENT_ID='kakao-client-id',
    KAKAO_OAUTH_CLIENT_SECRET='kakao-client-secret',
    KAKAO_OAUTH_REDIRECT_URI='http://localhost:8000/api/v1/auth/oauth/kakao/callback',
    FRONTEND_BASE_URL=FRONTEND_BASE_URL,
    FRONTEND_OAUTH_CALLBACK_PATH=FRONTEND_OAUTH_CALLBACK_PATH,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'oauth-tests'}},
)


def google_profile(**overrides):
    base = {
        'provider_user_id': 'google-uid-1',
        'email': 'newuser@example.com',
        'email_verified': True,
        'name': 'New Google User',
    }
    base.update(overrides)
    return base


def kakao_profile(**overrides):
    base = {
        'provider_user_id': 'kakao-uid-1',
        'email': 'newkakao@example.com',
        'email_verified': True,
        'name': 'New Kakao User',
    }
    base.update(overrides)
    return base


@override_settings(**OAUTH_SETTINGS)
class OAuthCallbackRedirectTests(APITestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    # ----- helpers -----
    def _state_for(self, provider, next_path='/mypage'):
        return build_authorization_url(provider, next_path=next_path)['state']

    def _callback(self, provider, *, profile, next_path='/mypage', code='auth-code'):
        with mock.patch(
            'apps.accounts.views_oauth.exchange_code_for_profile',
            return_value=profile,
        ):
            return self.client.get(
                f'/api/v1/auth/oauth/{provider}/callback',
                {'code': code, 'state': self._state_for(provider, next_path)},
            )

    def _assert_redirects_with_code(self, response):
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        location = response['Location']
        self.assertTrue(location.startswith(f'{FRONTEND_BASE_URL}{FRONTEND_OAUTH_CALLBACK_PATH}'))
        # 토큰은 URL 에 절대 포함되지 않는다.
        self.assertNotIn('access_token', location)
        self.assertNotIn('refresh', location)
        query = parse_qs(urlparse(location).query)
        self.assertIn('code', query)
        self.assertNotIn('error', query)
        return query['code'][0]

    def _assert_redirects_with_error(self, response, expected_error):
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        query = parse_qs(urlparse(response['Location']).query)
        self.assertEqual(query.get('error', [None])[0], expected_error)
        self.assertNotIn('code', query)

    def _exchange(self, code):
        return self.client.post('/api/v1/auth/oauth/exchange', {'code': code}, format='json')

    def _make_required_terms(self):
        TermsDocument.objects.update(is_active=False)
        TermsDocument.objects.create(kind=TermsDocument.KIND_TERMS, version='t-1', is_required=True, is_active=True)
        TermsDocument.objects.create(kind=TermsDocument.KIND_PRIVACY, version='p-1', is_required=True, is_active=True)

    def _disable_required_terms(self):
        TermsDocument.objects.filter(is_required=True).update(is_active=False)

    # ----- existing user login -----
    def test_google_existing_user_login_redirects_then_exchanges(self):
        user = User.objects.create(email='newuser@example.com', name='G', is_verified=True, status='active')
        SocialAccount.objects.create(user=user, provider='google', provider_user_id='google-uid-1', provider_email=user.email)

        response = self._callback('google', profile=google_profile())
        code = self._assert_redirects_with_code(response)

        exchange = self._exchange(code)
        self.assertEqual(exchange.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', exchange.data)
        self.assertEqual(exchange.data['token_type'], 'Bearer')
        self.assertFalse(exchange.data['created'])
        self.assertEqual(exchange.data['next_path'], '/mypage')
        self.assertIn('refresh_token', exchange.cookies)
        # 동일 사용자, 신규 생성 없음
        self.assertEqual(User.objects.filter(email='newuser@example.com').count(), 1)

    def test_kakao_existing_user_login(self):
        user = User.objects.create(email='newkakao@example.com', name='K', is_verified=True, status='active')
        SocialAccount.objects.create(user=user, provider='kakao', provider_user_id='kakao-uid-1', provider_email=user.email)

        response = self._callback('kakao', profile=kakao_profile())
        code = self._assert_redirects_with_code(response)
        exchange = self._exchange(code)
        self.assertEqual(exchange.status_code, status.HTTP_200_OK)
        self.assertFalse(exchange.data['created'])

    # ----- new user signup -----
    def test_google_new_user_signup_with_required_terms_redirects_to_social_terms(self):
        self._make_required_terms()
        response = self._callback('google', profile=google_profile(email='brandnew@example.com'))
        code = self._assert_redirects_with_code(response)

        user = User.objects.get(email='brandnew@example.com')
        self.assertTrue(SocialAccount.objects.filter(user=user, provider='google').exists())
        self.assertFalse(user.has_usable_password())

        exchange = self._exchange(code)
        self.assertEqual(exchange.status_code, status.HTTP_200_OK)
        self.assertTrue(exchange.data['created'])
        self.assertTrue(exchange.data['needs_terms'])
        self.assertEqual(exchange.data['next_path'], '/signup/social/terms')

    def test_kakao_new_user_signup_without_required_terms_goes_to_mypage(self):
        self._disable_required_terms()
        with mock.patch.object(User.objects, 'create_user', wraps=User.objects.create_user) as create_user:
            response = self._callback('kakao', profile=kakao_profile(email='kfresh@example.com'))
        code = self._assert_redirects_with_code(response)
        create_user.assert_called_once_with(
            email='kfresh@example.com',
            name='New Kakao User',
            password=None,
            is_verified=True,
            status='active',
        )
        exchange = self._exchange(code)
        self.assertEqual(exchange.status_code, status.HTTP_200_OK)
        self.assertTrue(exchange.data['created'])
        self.assertFalse(exchange.data['needs_terms'])
        self.assertEqual(exchange.data['next_path'], '/mypage')

    def test_repeat_login_does_not_create_duplicate_user_or_social(self):
        self._disable_required_terms()
        self._assert_redirects_with_code(self._callback('google', profile=google_profile(email='dup@example.com')))
        self._assert_redirects_with_code(self._callback('google', profile=google_profile(email='dup@example.com')))
        self.assertEqual(User.objects.filter(email='dup@example.com').count(), 1)
        self.assertEqual(SocialAccount.objects.filter(provider='google', provider_user_id='google-uid-1').count(), 1)

    # ----- account conflict (no silent auto-link) -----
    def test_same_email_existing_local_account_returns_conflict(self):
        User.objects.create(email='conflict@example.com', name='Local', is_verified=True, status='active')
        response = self._callback('google', profile=google_profile(email='conflict@example.com', provider_user_id='google-new'))
        self._assert_redirects_with_error(response, 'OAUTH_ACCOUNT_CONFLICT')
        # 자동 연결/생성 안 됨
        self.assertFalse(SocialAccount.objects.filter(provider='google', provider_user_id='google-new').exists())

    # ----- state / code / email / blocked -----
    def test_forged_state_redirects_with_state_invalid(self):
        with mock.patch('apps.accounts.views_oauth.exchange_code_for_profile', return_value=google_profile()):
            response = self.client.get(
                '/api/v1/auth/oauth/google/callback', {'code': 'x', 'state': 'forged-state'}
            )
        self._assert_redirects_with_error(response, 'OAUTH_STATE_INVALID')

    def test_expired_state_redirects_with_state_invalid(self):
        state = self._state_for('google')
        with mock.patch.object(oauth_service, 'OAUTH_STATE_MAX_AGE', -1), \
             mock.patch('apps.accounts.views_oauth.exchange_code_for_profile', return_value=google_profile()):
            response = self.client.get('/api/v1/auth/oauth/google/callback', {'code': 'x', 'state': state})
        self._assert_redirects_with_error(response, 'OAUTH_STATE_INVALID')

    def test_missing_code_redirects_with_callback_invalid(self):
        response = self.client.get('/api/v1/auth/oauth/google/callback', {'state': self._state_for('google')})
        self._assert_redirects_with_error(response, 'OAUTH_CALLBACK_INVALID')

    def test_provider_error_param_redirects_with_provider_error(self):
        response = self.client.get('/api/v1/auth/oauth/kakao/callback', {'error': 'access_denied'})
        self._assert_redirects_with_error(response, 'OAUTH_PROVIDER_ERROR')

    def test_unexpected_callback_error_is_logged_and_redirected(self):
        with mock.patch(
            'apps.accounts.views_oauth.exchange_code_for_profile',
            side_effect=RuntimeError('unexpected provider payload'),
        ), self.assertLogs('apps.accounts', level='ERROR') as logs:
            response = self.client.get(
                '/api/v1/auth/oauth/kakao/callback',
                {'code': 'x', 'state': self._state_for('kakao')},
            )
        self._assert_redirects_with_error(response, 'OAUTH_PROVIDER_ERROR')
        self.assertIn('oauth callback unexpected error provider=kakao', '\n'.join(logs.output))

    def test_missing_provider_email_redirects_with_email_required(self):
        response = self._callback('kakao', profile=kakao_profile(email=''))
        self._assert_redirects_with_error(response, 'OAUTH_EMAIL_REQUIRED')

    def test_blocked_user_redirects_with_account_blocked(self):
        user = User.objects.create(email='banned@example.com', name='B', is_verified=True, status='banned')
        SocialAccount.objects.create(user=user, provider='google', provider_user_id='google-uid-1', provider_email=user.email)
        response = self._callback('google', profile=google_profile(email='banned@example.com'))
        self._assert_redirects_with_error(response, 'OAUTH_ACCOUNT_BLOCKED')

    # ----- token never in URL -----
    def test_success_redirect_has_no_tokens_in_url(self):
        self._disable_required_terms()
        response = self._callback('google', profile=google_profile(email='clean@example.com'))
        location = response['Location']
        self.assertNotIn('access_token', location)
        self.assertNotIn('Bearer', location)


@override_settings(**OAUTH_SETTINGS)
class OAuthProviderResponseTests(APITestCase):
    def test_invalid_token_json_is_wrapped_as_provider_error(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError('invalid json')
        with mock.patch('apps.accounts.services.oauth.requests.post', return_value=response):
            with self.assertRaises(oauth_service.OAuthProviderResponseError):
                oauth_service.exchange_code_for_profile('kakao', code='x')

    def test_non_object_token_json_is_wrapped_as_provider_error(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = []
        with mock.patch('apps.accounts.services.oauth.requests.post', return_value=response):
            with self.assertRaises(oauth_service.OAuthProviderResponseError):
                oauth_service.exchange_code_for_profile('kakao', code='x')

    def test_non_object_profile_json_is_wrapped_as_provider_error(self):
        token_response = mock.Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {'access_token': 'provider-token'}
        profile_response = mock.Mock()
        profile_response.raise_for_status.return_value = None
        profile_response.json.return_value = []
        with mock.patch('apps.accounts.services.oauth.requests.post', return_value=token_response), \
             mock.patch('apps.accounts.services.oauth.requests.get', return_value=profile_response):
            with self.assertRaises(oauth_service.OAuthProviderResponseError):
                oauth_service.exchange_code_for_profile('kakao', code='x')


class LegacyUserManagerCompatibilityTests(APITestCase):
    def test_legacy_insert_includes_required_onboarding_version(self):
        cursor = mock.Mock()
        cursor.lastrowid = 123
        cursor_context = mock.MagicMock()
        cursor_context.__enter__.return_value = cursor

        with mock.patch.object(User.objects, '_has_legacy_role_column', return_value=True), \
             mock.patch('apps.accounts.models.connection.cursor', return_value=cursor_context):
            user = User.objects.create_user(
                email='legacy-social@example.com',
                name='Legacy Social',
                password=None,
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn('onboarding_version', sql)
        self.assertIn(user.onboarding_version, params)
        self.assertEqual(user.id, 123)


class OAuthExchangeCodeUnitTests(APITestCase):
    def setUp(self):
        cache.clear()

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'xchg'}})
    def test_single_use_then_used(self):
        code = issue_exchange_code(user_id=1, provider='google', next_path='/mypage', created=False, needs_terms=False)
        first = consume_exchange_code(code)
        self.assertEqual(first['user_id'], 1)
        with self.assertRaises(OAuthExchangeCodeUsed):
            consume_exchange_code(code)

    def test_invalid_code_raises(self):
        with self.assertRaises(OAuthExchangeCodeInvalid):
            consume_exchange_code('not-a-real-signed-token')

    @override_settings(
        OAUTH_EXCHANGE_CODE_TTL_SECONDS=-1,
        CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'xchg2'}},
    )
    def test_expired_code_raises(self):
        code = issue_exchange_code(user_id=1, provider='google', next_path='/mypage', created=False, needs_terms=False)
        with self.assertRaises(OAuthExchangeCodeExpired):
            consume_exchange_code(code)


class SanitizeNextPathTests(APITestCase):
    def test_allows_internal_path(self):
        self.assertEqual(sanitize_next_path('/mypage'), '/mypage')
        self.assertEqual(sanitize_next_path('/signup/social/terms'), '/signup/social/terms')

    def test_blocks_open_redirect(self):
        self.assertEqual(sanitize_next_path('https://evil.com'), '/mypage')
        self.assertEqual(sanitize_next_path('//evil.com'), '/mypage')
        self.assertEqual(sanitize_next_path('/\\evil.com'), '/mypage')
        self.assertEqual(sanitize_next_path('javascript:alert(1)'), '/mypage')
        self.assertEqual(sanitize_next_path(''), '/mypage')
        self.assertEqual(sanitize_next_path(None), '/mypage')

    @override_settings(**OAUTH_SETTINGS)
    def test_start_rejects_external_next(self):
        data = build_authorization_url('google', next_path='https://evil.com')
        self.assertEqual(data['next_path'], '/mypage')
