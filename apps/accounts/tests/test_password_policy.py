"""
비밀번호 정책(P0-2) — 회원가입 엔드포인트 검증 테스트.

SignupSerializer.validate() 가 AUTH_PASSWORD_VALIDATORS 를 적용해
약한 비밀번호를 400 으로 거부하는지 확인한다.

쉬운 예시 차단 대상:
- 12345678   (숫자만 / 영문·특수문자 없음)
- qwer1234    (특수문자 없음)
- password123 (CommonPasswordValidator)
- 이메일/이름 포함 비밀번호 (UserAttributeSimilarityValidator)
"""
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

# 로컬 메모리 메일 백엔드 — 회원가입 시 인증번호 메일 발송이 실제 SMTP 로 나가지 않도록.
LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class PasswordPolicyTests(APITestCase):
    signup_url = "/api/v1/auth/signup"

    def _signup(self, password, email="pw.user@example.com", name="홍길동"):
        return self.client.post(
            self.signup_url, {"email": email, "name": name, "password": password}
        )

    def test_rejects_numeric_only(self):
        res = self._signup("12345678")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email="pw.user@example.com").exists())

    def test_rejects_no_special_char(self):
        res = self._signup("qwer1234")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_common_password(self):
        res = self._signup("password123")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_repeated_chars(self):
        # 같은 문자 3연속 (aaa) 차단
        res = self._signup("aaaQwe!9")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_password_containing_email(self):
        # 비밀번호가 이메일 local-part(stronguser)를 포함 → 유사도 검증 차단
        res = self._signup("Stronguser!1", email="stronguser@example.com")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accepts_strong_password(self):
        res = self._signup("StrongPw!234", email="good.user@example.com")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="good.user@example.com").exists())


@override_settings(EMAIL_CODE_TTL_SECONDS=600)
class EmailCodeTTLConfigTests(APITestCase):
    """이메일 인증번호 만료시간이 10분(600초) 기준으로 적용되는지 확인."""

    def test_ttl_is_ten_minutes(self):
        from apps.accounts import codes as codes_mod

        self.assertEqual(codes_mod.get_ttl_seconds(), 600)
