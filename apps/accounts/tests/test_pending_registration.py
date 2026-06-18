import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import PendingRegistration, User


LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD = "QaTestPw!234"


def code_from_outbox(email):
    for message in reversed(mail.outbox):
        if email in message.to:
            found = re.search(r"(\d{6})", message.body)
            if found:
                return found.group(1)
    return None


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class PendingRegistrationFlowTests(APITestCase):
    signup_url = "/api/v1/auth/signup"
    verify_url = "/api/v1/auth/verify-email"
    resend_url = "/api/v1/auth/verify-email/resend"

    def signup_payload(self, email="pending@example.com", **overrides):
        payload = {
            "email": email,
            "name": "Pending User",
            "password": PASSWORD,
            "terms_version": "terms-2026-06",
            "privacy_version": "privacy-2026-06",
            "terms_agreed": True,
            "privacy_agreed": True,
            "marketing_agreed": False,
        }
        payload.update(overrides)
        return payload

    def signup(self, email="pending@example.com", **overrides):
        return self.client.post(self.signup_url, self.signup_payload(email=email, **overrides))

    def test_signup_creates_pending_without_user(self):
        response = self.signup()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("user_id", response.data)
        self.assertEqual(response.data["expires_in"], 600)
        self.assertEqual(response.data["resend_after"], 60)
        self.assertFalse(User.objects.filter(email="pending@example.com").exists())
        pending = PendingRegistration.objects.get(email="pending@example.com")
        self.assertTrue(pending.password_hash.startswith("pbkdf2_"))
        self.assertNotEqual(pending.password_hash, PASSWORD)
        self.assertEqual(pending.terms_version, "terms-2026-06")
        self.assertEqual(pending.privacy_version, "privacy-2026-06")
        self.assertTrue(pending.terms_agreed)
        self.assertTrue(pending.privacy_agreed)
        self.assertFalse(pending.marketing_agreed)
        self.assertIsNotNone(pending.agreed_at)

    def test_signup_email_send_failure_does_not_create_user(self):
        with patch("apps.accounts.views.send_verification_code_email", side_effect=RuntimeError("smtp down")):
            response = self.signup("smtp-fail@example.com")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "EMAIL_SEND_FAILED")
        self.assertFalse(User.objects.filter(email="smtp-fail@example.com").exists())
        pending = PendingRegistration.objects.get(email="smtp-fail@example.com")
        self.assertEqual(pending.code_hash, "")

    def test_verify_success_creates_exactly_one_user_and_preserves_password_hash(self):
        self.signup()
        pending = PendingRegistration.objects.get(email="pending@example.com")
        original_hash = pending.password_hash
        code = code_from_outbox("pending@example.com")

        response = self.client.post(self.verify_url, {"email": "pending@example.com", "code": code})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.filter(email="pending@example.com").count(), 1)
        user = User.objects.get(email="pending@example.com")
        self.assertTrue(user.is_verified)
        self.assertEqual(user.password, original_hash)
        self.assertTrue(user.check_password(PASSWORD))

    def test_duplicate_verify_does_not_create_duplicate_user(self):
        self.signup()
        code = code_from_outbox("pending@example.com")
        first = self.client.post(self.verify_url, {"email": "pending@example.com", "code": code})
        second = self.client.post(self.verify_url, {"email": "pending@example.com", "code": code})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "REGISTRATION_ALREADY_VERIFIED")
        self.assertEqual(User.objects.filter(email="pending@example.com").count(), 1)

    def test_wrong_code_does_not_create_user(self):
        self.signup()
        response = self.client.post(self.verify_url, {"email": "pending@example.com", "code": "000000"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "VERIFY_CODE_INVALID")
        self.assertFalse(User.objects.filter(email="pending@example.com").exists())

    def test_expired_code_does_not_create_user(self):
        self.signup()
        code = code_from_outbox("pending@example.com")
        PendingRegistration.objects.filter(email="pending@example.com").update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.client.post(self.verify_url, {"email": "pending@example.com", "code": code})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "VERIFY_CODE_EXPIRED")
        self.assertFalse(User.objects.filter(email="pending@example.com").exists())

    @override_settings(EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0)
    def test_resend_does_not_create_user(self):
        self.signup()
        response = self.client.post(self.resend_url, {"email": "pending@example.com"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.filter(email="pending@example.com").exists())
        self.assertEqual(PendingRegistration.objects.filter(email="pending@example.com").count(), 1)

    def test_required_terms_are_enforced(self):
        response = self.signup("terms-fail@example.com", terms_agreed=False)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PendingRegistration.objects.filter(email="terms-fail@example.com").exists())
        self.assertFalse(User.objects.filter(email="terms-fail@example.com").exists())

    def test_required_privacy_is_enforced(self):
        response = self.signup("privacy-fail@example.com", privacy_agreed=False)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PendingRegistration.objects.filter(email="privacy-fail@example.com").exists())
        self.assertFalse(User.objects.filter(email="privacy-fail@example.com").exists())

    def test_legacy_unverified_user_is_not_converted_to_pending(self):
        legacy = User.objects.create_user(email="legacy@example.com", name="Legacy", password=PASSWORD)
        self.assertFalse(legacy.is_verified)

        response = self.signup("legacy@example.com")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("user_id", response.data)
        self.assertFalse(PendingRegistration.objects.filter(email="legacy@example.com").exists())
        self.assertEqual(User.objects.filter(email="legacy@example.com").count(), 1)
        self.assertFalse(User.objects.get(email="legacy@example.com").is_verified)
