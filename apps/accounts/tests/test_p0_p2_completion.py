import re

from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import PointHistory, TermsAgreement, User
from apps.accounts.services.points import apply_point_policy


LOCMEM_EMAIL = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD = 'QaTestPw!234'


def code_from_outbox(email):
    for message in reversed(mail.outbox):
        if email in message.to:
            found = re.search(r'(\d{6})', message.body)
            if found:
                return found.group(1)
    return None


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, EMAIL_CODE_RESEND_COOLDOWN_SECONDS=0)
class TermsAgreementSignupTests(APITestCase):
    def test_pending_signup_verification_records_terms_history_and_reward(self):
        signup = self.client.post(
            '/api/v1/auth/signup',
            {
                'email': 'terms-history@example.com',
                'name': 'Terms User',
                'password': PASSWORD,
                'terms_version': 'terms-2026-06',
                'privacy_version': 'privacy-2026-06',
                'terms_agreed': True,
                'privacy_agreed': True,
                'marketing_agreed': False,
            },
            format='json',
        )
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)
        code = code_from_outbox('terms-history@example.com')

        verify = self.client.post(
            '/api/v1/auth/verify-email',
            {'email': 'terms-history@example.com', 'code': code},
            format='json',
        )

        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        user = User.objects.get(email='terms-history@example.com')
        self.assertEqual(TermsAgreement.objects.filter(user=user).count(), 3)
        self.assertTrue(TermsAgreement.objects.filter(user=user, kind='TERMS', agreed=True).exists())
        self.assertTrue(PointHistory.objects.filter(user=user, reason_code='AUTH.EMAIL_VERIFIED').exists())


class OAuthContractTests(APITestCase):
    def test_start_returns_env_required_when_provider_is_not_configured(self):
        response = self.client.get('/api/v1/auth/oauth/google/start')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['status'], 'ENV_REQUIRED')
        self.assertEqual(response.data['code'], 'OAUTH_PROVIDER_NOT_CONFIGURED')

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        GOOGLE_OAUTH_REDIRECT_URI='http://localhost/oauth/google/callback',
    )
    def test_start_builds_authorization_url_with_state(self):
        response = self.client.get('/api/v1/auth/oauth/google/start', {'next': '/mypage'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('accounts.google.com', response.data['auth_url'])
        self.assertTrue(response.data['state'])
        self.assertEqual(response.data['next_path'], '/mypage')


class PointPolicyTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='policy@example.com',
            password=PASSWORD,
            name='Policy User',
            is_verified=True,
        )

    def test_account_once_policy_prevents_duplicate_reward(self):
        first = apply_point_policy(
            user=self.user,
            reason_code='PROFILE.COMPLETED',
            reference_id='profile-1',
            idempotency_key='profile-completed-policy',
        )
        self.assertTrue(first.created)

        with self.assertRaises(ValueError):
            apply_point_policy(
                user=self.user,
                reason_code='PROFILE.COMPLETED',
                reference_id='profile-2',
                idempotency_key='profile-completed-policy-2',
            )

        self.user.refresh_from_db()
        self.assertEqual(self.user.point_balance, 500)
