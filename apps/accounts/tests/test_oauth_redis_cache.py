"""OAuth 일회용 교환 코드 캐시 동작 검증 (캐시 백엔드 비의존).

이 테스트는 LocMemCache 로 결정성 있게 실행된다(외부 Redis 불필요). 운영 Redis 에서도
동일 계약(단일 사용/만료/위조 구분, Key·Value 에 토큰·이메일 미포함)이 성립한다.
다중 worker(프로세스) 간 실제 공유는 실제 Redis 가 필요하므로 별도 수동/ENV 검증 대상이다.
"""
from django.core import signing
from django.test import SimpleTestCase, override_settings

from apps.accounts.services.oauth import (
    OAUTH_EXCHANGE_SALT,
    OAuthExchangeCodeExpired,
    OAuthExchangeCodeInvalid,
    OAuthExchangeCodeUsed,
    _exchange_cache_key,
    consume_exchange_code,
    issue_exchange_code,
)
from django.core.cache import cache

LOCMEM = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'oauth-redis-cache-tests',
    }
}


@override_settings(CACHES=LOCMEM, OAUTH_EXCHANGE_CODE_TTL_SECONDS=120)
class ExchangeCodeContractTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_issue_then_consume_returns_payload(self):
        code = issue_exchange_code(user_id=42, provider='google', next_path='/mypage', created=True, needs_terms=False)
        payload = consume_exchange_code(code)
        self.assertEqual(payload['user_id'], 42)
        self.assertEqual(payload['provider'], 'google')
        self.assertEqual(payload['next_path'], '/mypage')

    def test_single_use_second_consume_raises_used(self):
        code = issue_exchange_code(user_id=1, provider='kakao', next_path='/mypage', created=False, needs_terms=False)
        consume_exchange_code(code)
        with self.assertRaises(OAuthExchangeCodeUsed):
            consume_exchange_code(code)

    def test_invalid_code_raises(self):
        with self.assertRaises(OAuthExchangeCodeInvalid):
            consume_exchange_code('totally-not-a-signed-token')

    @override_settings(OAUTH_EXCHANGE_CODE_TTL_SECONDS=-1)
    def test_expired_code_raises(self):
        code = issue_exchange_code(user_id=1, provider='google', next_path='/mypage', created=False, needs_terms=False)
        with self.assertRaises(OAuthExchangeCodeExpired):
            consume_exchange_code(code)

    def test_cache_value_has_no_email_or_tokens(self):
        """Cache Value 에는 user_id/provider/next_path/created/needs_terms 만 저장된다.
        이메일·access/refresh/Provider 토큰은 포함되지 않는다(보안 요구사항)."""
        code = issue_exchange_code(user_id=7, provider='google', next_path='/mypage', created=True, needs_terms=True)
        jti = signing.loads(code, salt=OAUTH_EXCHANGE_SALT)['jti']
        raw = cache.get(_exchange_cache_key(jti))
        self.assertEqual(set(raw.keys()), {'user_id', 'provider', 'next_path', 'created', 'needs_terms'})
        blob = str(raw).lower()
        for forbidden in ('@', 'access_token', 'refresh', 'bearer', 'password', 'secret'):
            self.assertNotIn(forbidden, blob)

    def test_cache_key_is_opaque_and_has_no_pii(self):
        """Cache Key 는 무작위 jti 기반이며 이메일/Provider 토큰을 포함하지 않는다."""
        code = issue_exchange_code(user_id=7, provider='kakao', next_path='/mypage', created=False, needs_terms=False)
        jti = signing.loads(code, salt=OAUTH_EXCHANGE_SALT)['jti']
        key = _exchange_cache_key(jti)
        self.assertTrue(key.startswith('oauth:exchange:'))
        self.assertNotIn('@', key)

    def test_value_visible_via_independent_lookup(self):
        """발급 직후 별도 조회 경로에서도 동일 코드가 보인다(요청 로컬 아님 → 공유 캐시 의미).
        실제 다중 프로세스 공유는 Redis 필요(수동/ENV 검증)."""
        code = issue_exchange_code(user_id=9, provider='google', next_path='/mypage', created=False, needs_terms=False)
        jti = signing.loads(code, salt=OAUTH_EXCHANGE_SALT)['jti']
        self.assertIsNotNone(cache.get(_exchange_cache_key(jti)))
