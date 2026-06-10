from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from apps.accounts.models import User

PW = "QaTestPw!234"

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MeEndpointTests(APITestCase):
    login_url = "/api/v1/auth/login"
    me_url = "/api/v1/auth/me"

    def _verified(self, email, name):
        u = User.objects.create_user(email=email, name=name, password=PW)
        u.is_verified = True
        u.save()
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
