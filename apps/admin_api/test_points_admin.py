from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PointHistory

User = get_user_model()


class AdminPointAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-points@example.com",
            password="testpass123",
            name="Admin",
            is_verified=True,
            is_staff=True,
        )
        self.member = User.objects.create_user(
            email="member-points@example.com",
            password="testpass123",
            name="Member",
            is_verified=True,
        )
        access = str(RefreshToken.for_user(self.admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_admin_adjusts_points_and_audit_visible_in_history(self):
        response = self.client.post(
            f"/api/v1/admin/members/{self.member.id}/points/adjust",
            {"amount": 250, "reason": "QA adjustment", "idempotency_key": "admin-adjust-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["balance_after"], 250)
        self.member.refresh_from_db()
        self.assertEqual(self.member.point_balance, 250)

        duplicate = self.client.post(
            f"/api/v1/admin/members/{self.member.id}/points/adjust",
            {"amount": 250, "reason": "QA adjustment", "idempotency_key": "admin-adjust-1"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.point_balance, 250)

        history = self.client.get("/api/v1/admin/points/history", {"user_id": self.member.id})
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["total"], 1)
        self.assertEqual(history.data["results"][0]["transaction_type"], PointHistory.TRANSACTION_ADMIN)

    def test_admin_adjust_requires_reason(self):
        response = self.client.post(
            f"/api/v1/admin/members/{self.member.id}/points/adjust",
            {"amount": 10, "reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
