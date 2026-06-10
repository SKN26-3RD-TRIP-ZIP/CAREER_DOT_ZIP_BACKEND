from rest_framework import status
from rest_framework.test import APITestCase
from apps.accounts.models import User

PW = "QaTestPw!234"


class MemberDetailTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="admin@example.com", name="관리자", password=PW)
        self.admin.is_verified = True; self.admin.role = "admin"; self.admin.is_staff = True
        self.admin.save()
        self.member = User.objects.create_user(email="m@example.com", name="회원", password=PW)
        self.member.is_verified = True; self.member.save()

    def _token(self, email):
        return self.client.post("/api/v1/auth/login", {"email": email, "password": PW}).data["access_token"]

    def test_admin_can_get_member_detail(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token('admin@example.com')}")
        res = self.client.get(f"/api/v1/admin/members/{self.member.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["email"], "m@example.com")
        for key in ("interview_count", "completed_interview_count", "report_count", "is_verified"):
            self.assertIn(key, res.data)

    def test_normal_user_forbidden(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token('m@example.com')}")
        res = self.client.get(f"/api/v1/admin/members/{self.admin.id}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_blocked(self):
        self.client.credentials()
        res = self.client.get(f"/api/v1/admin/members/{self.member.id}")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_member_404(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token('admin@example.com')}")
        res = self.client.get("/api/v1/admin/members/999999")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
