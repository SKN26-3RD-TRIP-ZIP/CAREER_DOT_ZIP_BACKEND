from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.input.services.jd_url_analyzer import JDURLBlocked, validate_public_url


class JDURLSecurityTests(APITestCase):
    def test_localhost_url_is_blocked(self):
        with self.assertRaises(JDURLBlocked):
            validate_public_url('http://localhost:8000/jobs/1')


class JDOCRContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='ocr@example.com',
            password='Password123!',
            name='OCR User',
            is_verified=True,
        )
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    def test_image_ocr_without_provider_returns_env_required(self):
        upload = SimpleUploadedFile('job.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')

        response = self.client.post('/api/v1/jds/ocr', {'file': upload}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['status'], 'ENV_REQUIRED')
        self.assertEqual(response.data['code'], 'OCR_PROVIDER_NOT_CONFIGURED')
