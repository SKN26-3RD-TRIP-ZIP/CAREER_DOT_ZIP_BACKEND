from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from apps.accounts.models import TermsDocument, User
from apps.accounts.services.terms import record_terms_agreement
from apps.input.models import UserProfile

PW = "QaTestPw!234"

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MeEndpointTests(APITestCase):
    login_url = "/api/v1/auth/login"
    me_url = "/api/v1/auth/me"

    def _verified(self, email, name, *, agree_terms=True):
        u = User.objects.create_user(email=email, name=name, password=PW)
        u.is_verified = True
        u.save()
        if agree_terms:
            for document in TermsDocument.objects.filter(is_active=True, is_required=True):
                record_terms_agreement(
                    user=u,
                    kind=document.kind,
                    version=document.version,
                    agreed=True,
                    is_required=True,
                    source='SIGNUP',
                )
        return u

    def _login_token(self, email):
        res = self.client.post(self.login_url, {"email": email, "password": PW})
        return res.data["access_token"]

    def test_me_returns_logged_in_user(self):
        self._verified("a@example.com", "사용자A")
        token = self._login_token("a@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        res = self.client.get(self.me_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["email"], "a@example.com")
        self.assertEqual(res.data["name"], "사용자A")
        self.assertTrue(res.data["onboarding"]["required"])
        self.assertEqual(res.data["next_path"], "/input/onboarding/1")
        self.assertFalse(res.data["profile"]["exists"])

    def test_me_distinct_per_account(self):
        self._verified("a@example.com", "사용자A")
        self._verified("b@example.com", "사용자B")
        # A 로그인 → A
        ta = self._login_token("a@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {ta}")
        self.assertEqual(self.client.get(self.me_url).data["name"], "사용자A")
        # B 토큰 → B (이전 사용자 잔존 없음)
        tb = self._login_token("b@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tb}")
        self.assertEqual(self.client.get(self.me_url).data["name"], "사용자B")

    def test_me_requires_auth(self):
        self.client.credentials()
        res = self.client.get(self.me_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_prioritizes_required_terms_before_onboarding(self):
        self._verified("missing-terms@example.com", "약관미동의", agree_terms=False)
        token = self._login_token("missing-terms@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        res = self.client.get(self.me_url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["terms"]["required"])
        self.assertEqual(res.data["next_path"], "/signup/social/terms")

    def test_me_returns_mypage_next_path_when_profile_complete(self):
        user = self._verified("profiled@example.com", "프로필")
        user.onboarding_completed_at = timezone.now()
        user.save(update_fields=["onboarding_completed_at"])
        UserProfile.objects.create(
            user=user,
            career_type="신입",
            major_type="전공",
            desired_job="백엔드",
            career_year=0,
        )
        token = self._login_token("profiled@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        res = self.client.get(self.me_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["profile"]["exists"])
        self.assertTrue(res.data["profile"]["is_complete"])
        self.assertFalse(res.data["onboarding"]["required"])
        self.assertEqual(res.data["next_path"], "/mypage")

    def test_onboarding_complete_marks_user_and_updates_me_route(self):
        self._verified("onboard@example.com", "온보딩")
        token = self._login_token("onboard@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        before = self.client.get(self.me_url)
        self.assertEqual(before.status_code, status.HTTP_200_OK)
        self.assertTrue(before.data["onboarding"]["required"])

        complete = self.client.post("/api/v1/auth/onboarding/complete")
        self.assertEqual(complete.status_code, status.HTTP_200_OK)
        self.assertFalse(complete.data["onboarding"]["required"])

        after = self.client.get(self.me_url)
        self.assertEqual(after.status_code, status.HTTP_200_OK)
        self.assertFalse(after.data["onboarding"]["required"])
        self.assertEqual(after.data["next_path"], "/profile")

    def test_me_returns_admin_next_path_for_staff(self):
        user = self._verified("admin-next@example.com", "관리자")
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        token = self._login_token("admin-next@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        res = self.client.get(self.me_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["next_path"], "/admin/dashboard")
