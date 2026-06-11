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

from apps.accounts.models import User
from apps.accounts.tokens import generate_email_verification_token

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
            self.signup_url, {"email": email, "name": name, "password": PASSWORD}
        )

    def test_signup_success_creates_unverified_user(self):
        res = self._signup()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["email"], "qa.user@example.com")
        user = User.objects.get(email="qa.user@example.com")
        self.assertFalse(user.is_verified)

    def test_signup_sends_welcome_and_admin_emails(self):
        self._signup()
        # 환영(사용자) + 관리자 알림 = 2통
        self.assertEqual(len(mail.outbox), 2)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertIn("qa.user@example.com", recipients)
        self.assertIn("qa-admin@example.com", recipients)
        # 관리자 알림에 민감정보(비밀번호) 미포함
        admin_mail = next(m for m in mail.outbox if m.to[0] == "qa-admin@example.com")
        self.assertNotIn(PASSWORD, admin_mail.body)

    def test_duplicate_signup_returns_409(self):
        self._signup()
        res = self._signup()
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_unverified_login_returns_403(self):
        self._signup()
        res = self.client.post(self.login_url, {"email": "qa.user@example.com", "password": PASSWORD})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_verify_email_success_then_login_issues_token_and_cookie(self):
        self._signup()
        user = User.objects.get(email="qa.user@example.com")
        token = generate_email_verification_token(user)

        vres = self.client.get(self.verify_url, {"token": token})
        self.assertEqual(vres.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)

        lres = self.client.post(self.login_url, {"email": "qa.user@example.com", "password": PASSWORD})
        self.assertEqual(lres.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", lres.data)
        self.assertIn("refresh_token", lres.cookies)
        # refresh cookie 는 HttpOnly
        self.assertTrue(lres.cookies["refresh_token"]["httponly"])

    def test_verify_email_already_verified(self):
        self._signup()
        user = User.objects.get(email="qa.user@example.com")
        token = generate_email_verification_token(user)
        self.client.get(self.verify_url, {"token": token})
        # 두 번째 호출도 200 (이미 인증됨)
        res = self.client.get(self.verify_url, {"token": token})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_verify_email_invalid_token_400(self):
        res = self.client.get(self.verify_url, {"token": "not-a-valid-token"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_email_missing_token_400(self):
        res = self.client.get(self.verify_url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(EMAIL_VERIFICATION_TOKEN_MAX_AGE=-1)
    def test_verify_email_expired_token_400(self):
        # 토큰 생성 후 max_age=-1 로 즉시 만료 처리
        user = User.objects.create_user(email="exp@example.com", name="exp", password=PASSWORD)
        token = generate_email_verification_token(user)
        res = self.client.get(self.verify_url, {"token": token})
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


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class SeedAndAdminPermissionTests(APITestCase):
    login_url = "/api/v1/auth/login"
    members_url = "/api/v1/admin/members"

    def test_seed_qa_users_creates_admin_with_role(self):
        call_command("seed_qa_users", password=PASSWORD)
        admin = User.objects.get(email="tripdotzip@gmail.com")
        self.assertEqual(admin.role, "admin")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_verified)
        # 팀원/페르소나 계정 verified
        team = User.objects.get(email="parksoyun9084@gmail.com")
        self.assertTrue(team.is_verified)
        self.assertEqual(team.role, "user")

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
