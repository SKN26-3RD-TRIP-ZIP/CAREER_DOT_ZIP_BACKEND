"""
6자리 이메일 인증번호 — 서비스/엔드포인트 테스트.

- 발급/검증/만료/시도제한/재발송 쿨다운
- POST /auth/verify-email {email, code}

코드 평문은 로그/DB 저장하지 않으므로, 테스트는 issue_code() 반환값 또는 메일 본문으로 코드를 얻는다.
"""
import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import PendingRegistration, User, EmailVerificationCode
from apps.accounts import codes as codes_mod

LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD = "QaTestPw!234"


class CodeServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="svc@example.com", name="svc", password=PASSWORD)

    @override_settings(EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0)
    def test_issue_and_verify_ok(self):
        code = codes_mod.issue_code(self.user)
        self.assertRegex(code, r"^\d{6}$")
        self.assertEqual(codes_mod.verify_code(self.user, code), codes_mod.VerifyResult.OK)

    @override_settings(EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0)
    def test_wrong_code_invalid(self):
        code = codes_mod.issue_code(self.user)
        wrong = "111111" if code != "111111" else "222222"
        self.assertEqual(codes_mod.verify_code(self.user, wrong), codes_mod.VerifyResult.INVALID)

    @override_settings(EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0)
    def test_expired_code(self):
        codes_mod.issue_code(self.user)
        EmailVerificationCode.objects.filter(user=self.user, is_used=False).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(codes_mod.verify_code(self.user, "123456"), codes_mod.VerifyResult.EXPIRED)

    @override_settings(EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0, EMAIL_CODE_MAX_ATTEMPTS=2)
    def test_too_many_attempts(self):
        code = codes_mod.issue_code(self.user)
        wrong = "111111" if code != "111111" else "222222"
        self.assertEqual(codes_mod.verify_code(self.user, wrong), codes_mod.VerifyResult.INVALID)
        self.assertEqual(codes_mod.verify_code(self.user, wrong), codes_mod.VerifyResult.INVALID)
        # 2회 시도 후에는 정답이어도 TOO_MANY
        self.assertEqual(codes_mod.verify_code(self.user, code), codes_mod.VerifyResult.TOO_MANY)

    @override_settings(EMAIL_CODE_RESEND_COOLDOWN_SECONDS=300)
    def test_resend_cooldown(self):
        codes_mod.issue_code(self.user)
        with self.assertRaises(codes_mod.ResendCooldownError):
            codes_mod.issue_code(self.user)

    @override_settings(EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0)
    def test_reissue_invalidates_previous(self):
        code1 = codes_mod.issue_code(self.user)
        codes_mod.issue_code(self.user)  # 이전 코드 무효화
        self.assertEqual(codes_mod.verify_code(self.user, code1), codes_mod.VerifyResult.INVALID)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class VerifyEmailEndpointTests(APITestCase):
    signup_url = "/api/v1/auth/signup"
    verify_url = "/api/v1/auth/verify-email"

    def _signup(self, email="code.user@example.com"):
        return self.client.post(
            self.signup_url,
            {
                "email": email,
                "name": "[QA] 코드",
                "password": PASSWORD,
                "terms_agreed": True,
                "privacy_agreed": True,
                "marketing_agreed": False,
            },
        )

    @staticmethod
    def _code_for(email):
        for m in reversed(mail.outbox):
            if email in m.to:
                found = re.search(r"(\d{6})", m.body)
                if found:
                    return found.group(1)
        return None

    def test_signup_sends_code_email(self):
        self._signup()
        self.assertTrue(any("code.user@example.com" in m.to for m in mail.outbox))
        self.assertIsNotNone(self._code_for("code.user@example.com"))

    def test_signup_email_send_failure_returns_503(self):
        with patch("apps.accounts.views.send_verification_code_email", side_effect=RuntimeError("smtp down")):
            res = self._signup("mail.fail@example.com")

        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(res.data["code"], "EMAIL_SEND_FAILED")
        self.assertFalse(User.objects.filter(email="mail.fail@example.com").exists())
        self.assertFalse(
            EmailVerificationCode.objects.filter(
                user__email="mail.fail@example.com",
                is_used=False,
            ).exists()
        )

    def test_verify_success(self):
        self._signup()
        code = self._code_for("code.user@example.com")
        res = self.client.post(self.verify_url, {"email": "code.user@example.com", "code": code})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.get(email="code.user@example.com").is_verified)

    def test_verify_wrong_code_400(self):
        self._signup()
        code = self._code_for("code.user@example.com")
        wrong = "111111" if code != "111111" else "222222"
        res = self.client.post(self.verify_url, {"email": "code.user@example.com", "code": wrong})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_missing_fields_400(self):
        res = self.client.post(self.verify_url, {"email": "code.user@example.com"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(EMAIL_CODE_MAX_ATTEMPTS=5)
    def test_verify_max_attempts_five(self):
        self._signup("attempt.user@example.com")
        code = self._code_for("attempt.user@example.com")
        wrong = "111111" if code != "111111" else "222222"

        for _ in range(5):
            res = self.client.post(
                self.verify_url,
                {"email": "attempt.user@example.com", "code": wrong},
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        res = self.client.post(
            self.verify_url,
            {"email": "attempt.user@example.com", "code": code},
        )
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(res.data["code"], "VERIFY_TOO_MANY_ATTEMPTS")
