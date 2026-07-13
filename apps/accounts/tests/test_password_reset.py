from urllib.parse import parse_qs, urlparse

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User


LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"
OLD_PASSWORD = "QaOldPw!234"
NEW_PASSWORD = "QaNewPw!567"


@override_settings(
    EMAIL_BACKEND=LOCMEM_EMAIL,
    FRONTEND_BASE_URL="http://localhost:5173",
    PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS=60,
)
class PasswordResetTests(APITestCase):
    request_url = "/api/v1/auth/password-reset/request"
    confirm_url = "/api/v1/auth/password-reset/confirm"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="reset@example.com",
            name="reset-user",
            password=OLD_PASSWORD,
        )
        self.user.is_verified = True
        self.user.status = "active"
        self.user.save(update_fields=["is_verified", "status"])

    def _request_link(self):
        response = self.client.post(self.request_url, {"email": self.user.email})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        link = next(part for part in mail.outbox[0].body.split() if part.startswith("http"))
        query = parse_qs(urlparse(link).query)
        return query["uid"][0], query["token"][0]

    def test_request_sends_reset_link_for_existing_account(self):
        uid, token = self._request_link()
        self.assertTrue(uid)
        self.assertTrue(token)
        self.assertNotIn(OLD_PASSWORD, mail.outbox[0].body)

    def test_unknown_email_returns_same_response_without_sending(self):
        response = self.client.post(self.request_url, {"email": "unknown@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["code"], "PASSWORD_RESET_REQUEST_ACCEPTED")
        self.assertEqual(len(mail.outbox), 0)

    def test_confirm_changes_password_and_token_cannot_be_reused(self):
        uid, token = self._request_link()
        payload = {
            "uid": uid,
            "token": token,
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        }
        response = self.client.post(self.confirm_url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(OLD_PASSWORD))

        reused = self.client.post(self.confirm_url, payload)
        self.assertEqual(reused.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_rejects_mismatched_passwords(self):
        uid, token = self._request_link()
        response = self.client.post(
            self.confirm_url,
            {
                "uid": uid,
                "token": token,
                "password": NEW_PASSWORD,
                "password_confirm": "DifferentPw!890",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_applies_project_password_policy(self):
        uid, token = self._request_link()
        response = self.client.post(
            self.confirm_url,
            {
                "uid": uid,
                "token": token,
                "password": "password123",
                "password_confirm": "password123",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
