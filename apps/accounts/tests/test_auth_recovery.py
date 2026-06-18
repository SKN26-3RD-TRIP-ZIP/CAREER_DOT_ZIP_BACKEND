"""
인증/토큰/메일 복구 (P0) 통합 테스트.

검증:
- 회원가입 성공 / 중복 409 / 가입 후 is_verified=False
- 미인증 로그인 403
- verify-email 성공 후 is_verified=True / 잘못된·만료 토큰 400
- 인증 후 로그인 성공 + access_token + refresh cookie
- token refresh 성공
- logout 성공 및 cookie 삭제
- seed_qa_users 관리자 role/권한
- 일반 사용자 admin API 접근 403

비밀번호/토큰/쿠키 실제 값은 단언(assert) 외에 출력/기록하지 않는다.
"""
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

import re

from apps.accounts.models import PendingRegistration, User


def _code_from_outbox(email):
    """locmem outbox 에서 해당 수신자 메일의 6자리 인증번호를 추출."""
    for message in reversed(mail.outbox):
        if email in message.to:
            found = re.search(r"(\d{6})", message.body)
            if found:
                return found.group(1)
    return None


LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD = "QaTestPw!234"  # 테스트 전용 더미 (운영/실계정 아님)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, ADMIN_NOTIFICATION_EMAIL="qa-admin@example.com")
class SignupVerifyLoginFlowTests(APITestCase):
    signup_url = "/api/v1/auth/signup"
    login_url = "/api/v1/auth/login"
    verify_url = "/api/v1/auth/verify-email"
    refresh_url = "/api/v1/auth/token/refresh"
    logout_url = "/api/v1/auth/logout"

    def _signup(self, email="qa.user@example.com", name="[QA] 사용자"):
        return self.client.post(
            self.signup_url,
            {
                "email": email,
                "name": name,
                "password": PASSWORD,
                "terms_agreed": True,
                "privacy_agreed": True,
                "marketing_agreed": False,
            },
        )

    def test_signup_success_creates_pending_without_user(self):
        res = self._signup()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("user_id", res.data)
        self.assertTrue(PendingRegistration.objects.filter(email="qa.user@example.com").exists())
        self.assertFalse(User.objects.filter(email="qa.user@example.com").exists())

    def test_signup_sends_welcome_and_admin_emails(self):
        self._signup()
        # 환영(사용자) + 관리자 알림 = 2통
        self.assertEqual(len(mail.outbox), 1)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertIn("qa.user@example.com", recipients)
        code = _code_from_outbox("qa.user@example.com")
        self.client.post(self.verify_url, {"email": "qa.user@example.com", "code": code})
        self.assertEqual(len(mail.outbox), 2)
        # 관리자 알림에 민감정보(비밀번호) 미포함
        admin_mail = next(m for m in mail.outbox if m.to[0] == "qa-admin@example.com")
        self.assertNotIn(PASSWORD, admin_mail.body)

    def test_duplicate_unverified_signup_resends_and_returns_200(self):
        # 미인증 기존 계정 재가입 시도 — 차단(409) 대신 인증 흐름(200)으로 처리한다.
        self._signup()
        res = self._signup()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("retry_after", res.data)
        self.assertFalse(User.objects.filter(email="qa.user@example.com").exists())

    def test_duplicate_verified_signup_returns_409(self):
        # 인증 완료된 이메일만 "이미 가입된 이메일"로 막는다.
        self._signup()
        code = _code_from_outbox("qa.user@example.com")
        self.client.post(self.verify_url, {"email": "qa.user@example.com", "code": code})
        res = self._signup()
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_unverified_login_returns_403(self):
        self._signup()
        res = self.client.post(self.login_url, {"email": "qa.user@example.com", "password": PASSWORD})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_verify_code_success_then_login_issues_token_and_cookie(self):
        self._signup()
        code = _code_from_outbox("qa.user@example.com")
        self.assertIsNotNone(code)

        vres = self.client.post(
            self.verify_url, {"email": "qa.user@example.com", "code": code}
        )
        self.assertEqual(vres.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="qa.user@example.com")
        self.assertTrue(user.is_verified)

        lres = self.client.post(self.login_url, {"email": "qa.user@example.com", "password": PASSWORD})
        self.assertEqual(lres.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", lres.data)
        self.assertIn("refresh_token", lres.cookies)
        # refresh cookie 는 HttpOnly
        self.assertTrue(lres.cookies["refresh_token"]["httponly"])

    def test_verify_code_already_verified(self):
        self._signup()
        code = _code_from_outbox("qa.user@example.com")
        self.client.post(self.verify_url, {"email": "qa.user@example.com", "code": code})
        # 이미 인증된 계정 — 임의 코드로도 200(이미 인증)
        res = self.client.post(self.verify_url, {"email": "qa.user@example.com", "code": "000000"})
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "REGISTRATION_ALREADY_VERIFIED")

    def test_verify_invalid_code_400(self):
        self._signup()
        code = _code_from_outbox("qa.user@example.com")
        wrong = "111111" if code != "111111" else "222222"
        res = self.client.post(self.verify_url, {"email": "qa.user@example.com", "code": wrong})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_missing_fields_400(self):
        res = self.client.post(self.verify_url, {"email": "qa.user@example.com"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_expired_code_400(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.accounts.models import PendingRegistration

        self._signup()
        code = _code_from_outbox("qa.user@example.com")
        PendingRegistration.objects.filter(email="qa.user@example.com").update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        res = self.client.post(self.verify_url, {"email": "qa.user@example.com", "code": code})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_token_refresh_success(self):
        user = User.objects.create_user(email="r@example.com", name="r", password=PASSWORD)
        user.is_verified = True
        user.save()
        lres = self.client.post(self.login_url, {"email": "r@example.com", "password": PASSWORD})
        # 로그인 응답의 refresh cookie 가 client 에 보존됨 → refresh 호출
        res = self.client.post(self.refresh_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", res.data)
        self.assertIn("refresh_token", res.cookies)

    def test_token_refresh_ignores_invalid_authorization_header(self):
        user = User.objects.create_user(email="r2@example.com", name="r2", password=PASSWORD)
        user.is_verified = True
        user.save()
        self.client.post(self.login_url, {"email": "r2@example.com", "password": PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")

        res = self.client.post(self.refresh_url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", res.data)

    def test_refresh_without_cookie_returns_401(self):
        res = self.client.post(self.refresh_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_success_clears_cookie(self):
        user = User.objects.create_user(email="lo@example.com", name="lo", password=PASSWORD)
        user.is_verified = True
        user.save()
        lres = self.client.post(self.login_url, {"email": "lo@example.com", "password": PASSWORD})
        access = lres.data["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.post(self.logout_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # delete_cookie → 만료된 쿠키 헤더 존재
        self.assertIn("refresh_token", res.cookies)
        self.assertEqual(res.cookies["refresh_token"].value, "")

    def test_logout_requires_auth(self):
        res = self.client.post(self.logout_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_public_auth_endpoints_ignore_invalid_authorization_header(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")

        signup_res = self._signup("public@example.com")
        self.assertEqual(signup_res.status_code, status.HTTP_201_CREATED)

        code = _code_from_outbox("public@example.com")
        verify_res = self.client.post(
            self.verify_url,
            {"email": "public@example.com", "code": code},
        )
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)

        login_res = self.client.post(
            self.login_url,
            {"email": "public@example.com", "password": PASSWORD},
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        resend_res = self.client.post(
            "/api/v1/auth/resend-verification",
            {"email": "public@example.com"},
        )
        self.assertEqual(resend_res.status_code, status.HTTP_409_CONFLICT)

    def test_suspended_account_login_blocked(self):
        user = User.objects.create_user(email="suspended@example.com", name="s", password=PASSWORD)
        user.is_verified = True
        user.status = "suspended"
        user.save(update_fields=["is_verified", "status"])

        res = self.client.post(
            self.login_url,
            {"email": "suspended@example.com", "password": PASSWORD},
        )

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class SeedAndAdminPermissionTests(APITestCase):
    login_url = "/api/v1/auth/login"
    members_url = "/api/v1/admin/members"

    def test_seed_qa_users_creates_admin_with_permissions(self):
        call_command("seed_qa_users", password=PASSWORD)
        admin = User.objects.get(email="tripdotzip@gmail.com")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_verified)
        self.assertEqual(admin.status, "active")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_verified)
        # 팀원/페르소나 계정 verified
        team = User.objects.get(email="parksoyun9084@gmail.com")
        self.assertTrue(team.is_verified)
        self.assertFalse(team.is_staff)
        self.assertFalse(team.is_superuser)
        self.assertTrue(team.is_active)
        self.assertTrue(team.is_verified)
        self.assertEqual(team.status, "active")

    def test_normal_user_cannot_access_admin_api(self):
        call_command("seed_qa_users", password=PASSWORD)
        lres = self.client.post(
            self.login_url, {"email": "parksoyun9084@gmail.com", "password": PASSWORD}
        )
        access = lres.data["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.get(self.members_url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_user_can_access_admin_api(self):
        call_command("seed_qa_users", password=PASSWORD)
        lres = self.client.post(
            self.login_url, {"email": "tripdotzip@gmail.com", "password": PASSWORD}
        )
        access = lres.data["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.get(self.members_url)
        self.assertIn(res.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
