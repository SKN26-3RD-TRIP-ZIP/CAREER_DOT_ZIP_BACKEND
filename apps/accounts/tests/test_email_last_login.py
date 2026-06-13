"""
이메일 인증(재발송 포함) + 최근 로그인(last_login) 노출 테스트.

검증:
- 로그인 차단 기준이 is_verified 인지 (미인증 403 / 인증 200)
- /auth/me 응답에 last_login 포함 + 로그인 시 갱신
- /auth/resend-verification 동작(미인증 발송 / 인증·미가입은 발송 없이 동일 200 / 이메일 누락 400)

비밀번호/토큰/쿠키 실제 값은 단언(assert) 외에 출력/기록하지 않는다.
"""
from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD = "QaTestPw!234"  # 테스트 전용 더미


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class LoginVerifiedGateTests(APITestCase):
    login_url = "/api/v1/auth/login"

    def test_unverified_user_blocked_403(self):
        User.objects.create_user(email="u1@example.com", name="u1", password=PASSWORD)
        res = self.client.post(self.login_url, {"email": "u1@example.com", "password": PASSWORD})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_verified_non_staff_user_can_login(self):
        # is_staff=False 여도 is_verified=True 면 로그인 성공해야 한다 (이전 is_staff 버그 회귀 방지)
        u = User.objects.create_user(email="u2@example.com", name="u2", password=PASSWORD)
        u.is_verified = True
        u.save(update_fields=["is_verified"])
        self.assertFalse(u.is_staff)
        res = self.client.post(self.login_url, {"email": "u2@example.com", "password": PASSWORD})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", res.data)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class MeLastLoginTests(APITestCase):
    login_url = "/api/v1/auth/login"
    me_url = "/api/v1/auth/me"

    def _verified_login_token(self, email="me@example.com"):
        u = User.objects.create_user(email=email, name="me", password=PASSWORD)
        u.is_verified = True
        u.save(update_fields=["is_verified"])
        res = self.client.post(self.login_url, {"email": email, "password": PASSWORD})
        return res.data["access_token"]

    def test_me_includes_last_login_after_login(self):
        token = self._verified_login_token()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        res = self.client.get(self.me_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("last_login", res.data)
        # 로그인 시 update_last_login 으로 갱신되므로 None 이 아니어야 함
        self.assertIsNotNone(res.data["last_login"])


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class ResendVerificationTests(APITestCase):
    resend_url = "/api/v1/auth/resend-verification"

    def test_resend_for_unverified_sends_email(self):
        User.objects.create_user(email="rv1@example.com", name="rv1", password=PASSWORD)
        res = self.client.post(self.resend_url, {"email": "rv1@example.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("rv1@example.com", mail.outbox[0].to)

    def test_resend_for_verified_sends_nothing_but_200(self):
        u = User.objects.create_user(email="rv2@example.com", name="rv2", password=PASSWORD)
        u.is_verified = True
        u.save(update_fields=["is_verified"])
        res = self.client.post(self.resend_url, {"email": "rv2@example.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_for_unknown_email_returns_generic_200(self):
        # 이메일 열거 방지: 미가입도 동일 200, 메일 미발송
        res = self.client.post(self.resend_url, {"email": "nobody@example.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_requires_email(self):
        res = self.client.post(self.resend_url, {})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
