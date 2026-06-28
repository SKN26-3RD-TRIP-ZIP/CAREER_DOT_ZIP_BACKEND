from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.input.models import JobDescription


def _auth(client, user):
    access = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')


class JDPatchTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='owner@example.com', password='Password123!', name='Owner', is_verified=True)
        self.other = User.objects.create_user(email='other@example.com', password='Password123!', name='Other', is_verified=True)
        self.jd = JobDescription.objects.create(
            user=self.owner, company_name='Old Co', position='Old Pos', original_text='raw',
            input_method='URL', source_url='https://example.com/jobs/1', extraction_confidence=0.5,
            extracted_fields={'company_name': 'Old Co'}, job_requirements='old req',
        )
        self.url = f'/api/v1/jds/{self.jd.id}'

    def test_patch_owner_updates_allowed_fields(self):
        _auth(self.client, self.owner)
        res = self.client.patch(self.url, {'company_name': 'New Co', 'job_requirements': '3+ years'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.jd.refresh_from_db()
        self.assertEqual(self.jd.company_name, 'New Co')
        self.assertEqual(self.jd.job_requirements, '3+ years')
        self.assertEqual(self.jd.position, 'Old Pos')  # 미전달 필드 유지

    def test_patch_ignores_readonly_fields(self):
        _auth(self.client, self.owner)
        res = self.client.patch(self.url, {'source_url': 'https://evil.test', 'extraction_confidence': 0.99}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.jd.refresh_from_db()
        self.assertEqual(self.jd.source_url, 'https://example.com/jobs/1')  # 변경 안 됨
        self.assertEqual(self.jd.extraction_confidence, 0.5)

    def test_patch_other_user_404(self):
        _auth(self.client, self.other)
        res = self.client.patch(self.url, {'company_name': 'Hacked'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.jd.refresh_from_db()
        self.assertEqual(self.jd.company_name, 'Old Co')

    def test_patch_blank_company_rejected(self):
        _auth(self.client, self.owner)
        res = self.client.patch(self.url, {'company_name': ''}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_and_delete_still_work(self):
        _auth(self.client, self.owner)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_204_NO_CONTENT)

    def test_patch_requires_auth(self):
        res = self.client.patch(self.url, {'company_name': 'X'}, format='json')
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
