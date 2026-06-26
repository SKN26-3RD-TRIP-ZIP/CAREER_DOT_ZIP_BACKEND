from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PointHistory
from apps.accounts.services.points import (
    InsufficientPointsError,
    earn_points,
    refund_points,
    use_points,
)

User = get_user_model()


class PointServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="points@example.com",
            password="testpass123",
            name="Points",
            is_verified=True,
        )

    def test_earn_use_refund_and_balance(self):
        earn_points(user=self.user, amount=500, reason_code="PROFILE.COMPLETED")
        self.user.refresh_from_db()
        self.assertEqual(self.user.point_balance, 500)

        use_points(user=self.user, amount=100, reason_code="INTERVIEW.EXTRA_SESSION")
        self.user.refresh_from_db()
        self.assertEqual(self.user.point_balance, 400)

        refund_points(user=self.user, amount=100, reason_code="REPORT.REFUND")
        self.user.refresh_from_db()
        self.assertEqual(self.user.point_balance, 500)
        self.assertEqual(PointHistory.objects.filter(user=self.user).count(), 3)

    def test_idempotency_prevents_duplicate_earn(self):
        first = earn_points(
            user=self.user,
            amount=100,
            reason_code="AUTH.EMAIL_VERIFIED",
            idempotency_key="auth-email-verified-1",
        )
        second = earn_points(
            user=self.user,
            amount=100,
            reason_code="AUTH.EMAIL_VERIFIED",
            idempotency_key="auth-email-verified-1",
        )

        self.user.refresh_from_db()
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.history.id, second.history.id)
        self.assertEqual(self.user.point_balance, 100)

    def test_insufficient_points_blocks_debit(self):
        with self.assertRaises(InsufficientPointsError):
            use_points(user=self.user, amount=100, reason_code="INTERVIEW.EXTRA_SESSION")
        self.assertEqual(PointHistory.objects.filter(user=self.user).count(), 0)


class PointAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="points-api@example.com",
            password="testpass123",
            name="Points API",
            is_verified=True,
        )
        earn_points(user=self.user, amount=300, reason_code="INTERVIEW.COMPLETED")
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_my_points_balance_and_history(self):
        balance = self.client.get("/api/v1/users/me/points")
        self.assertEqual(balance.status_code, 200)
        self.assertEqual(balance.data["point_balance"], 300)

        history = self.client.get("/api/v1/users/me/points/history", {"page": 1, "size": 10})
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["total"], 1)
        self.assertEqual(history.data["results"][0]["amount"], 300)

    def test_points_require_auth(self):
        self.client.credentials()
        response = self.client.get("/api/v1/users/me/points")
        self.assertEqual(response.status_code, 401)
