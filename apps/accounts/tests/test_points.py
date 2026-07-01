from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PointHistory, PointPolicy
from apps.accounts.services.points import (
    InsufficientPointsError,
    apply_point_policy,
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

    def test_interview_completed_policy_awards_300_points_once_per_reference(self):
        first = apply_point_policy(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-1",
            idempotency_key="INTERVIEW.COMPLETED:session-1",
            description="interview completed",
        )
        second = apply_point_policy(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-1",
            idempotency_key="INTERVIEW.COMPLETED:session-1",
            description="interview completed",
        )

        self.user.refresh_from_db()
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.history.id, second.history.id)
        self.assertEqual(self.user.point_balance, 300)
        self.assertEqual(
            PointHistory.objects.filter(
                user=self.user,
                reason_code="INTERVIEW.COMPLETED",
                reference_id="session-1",
            ).count(),
            1,
        )

    def test_interview_completed_policy_blocks_other_reference_on_same_day(self):
        apply_point_policy(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-1",
            idempotency_key="INTERVIEW.COMPLETED:session-1",
            description="interview completed",
        )

        with self.assertRaises(ValueError):
            apply_point_policy(
                user=self.user,
                reason_code="INTERVIEW.COMPLETED",
                reference_id="session-2",
                idempotency_key="INTERVIEW.COMPLETED:session-2",
                description="interview completed",
            )

        self.user.refresh_from_db()
        self.assertEqual(self.user.point_balance, 300)
        self.assertEqual(
            PointHistory.objects.filter(
                user=self.user,
                reason_code="INTERVIEW.COMPLETED",
            ).count(),
            1,
        )

    def test_interview_completed_policy_allows_first_completion_on_next_day(self):
        apply_point_policy(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-1",
            idempotency_key="INTERVIEW.COMPLETED:session-1",
            description="interview completed",
        )
        PointHistory.objects.filter(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
        ).update(created_at=timezone.now() - timedelta(days=1))

        second = apply_point_policy(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-2",
            idempotency_key="INTERVIEW.COMPLETED:session-2",
            description="interview completed",
        )

        self.user.refresh_from_db()
        self.assertTrue(second.created)
        self.assertEqual(self.user.point_balance, 600)
        self.assertEqual(
            PointHistory.objects.filter(
                user=self.user,
                reason_code="INTERVIEW.COMPLETED",
            ).count(),
            2,
        )

    def test_interview_completed_daily_once_is_per_user(self):
        other_user = User.objects.create_user(
            email="points-other@example.com",
            password="testpass123",
            name="Points Other",
            is_verified=True,
        )
        apply_point_policy(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-owner",
            idempotency_key="INTERVIEW.COMPLETED:session-owner",
            description="interview completed",
        )
        other_result = apply_point_policy(
            user=other_user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-other",
            idempotency_key="INTERVIEW.COMPLETED:session-other",
            description="interview completed",
        )

        self.user.refresh_from_db()
        other_user.refresh_from_db()
        self.assertEqual(self.user.point_balance, 300)
        self.assertTrue(other_result.created)
        self.assertEqual(other_user.point_balance, 300)

    def test_apply_point_policy_prefers_active_db_policy(self):
        PointPolicy.objects.update_or_create(
            reason_code="INTERVIEW.COMPLETED",
            defaults={
                "transaction_type": PointHistory.TRANSACTION_EARN,
                "amount": 45,
                "daily_limit": None,
                "monthly_limit": None,
                "account_once": False,
                "per_reference_once": True,
                "is_active": True,
                "policy_version": "test-db-policy",
            },
        )

        result = apply_point_policy(
            user=self.user,
            reason_code="INTERVIEW.COMPLETED",
            reference_id="session-db-policy",
            idempotency_key="INTERVIEW.COMPLETED:session-db-policy",
            description="interview completed",
        )

        self.user.refresh_from_db()
        self.assertTrue(result.created)
        self.assertEqual(result.history.amount, 45)
        self.assertEqual(result.history.policy_version, "test-db-policy")
        self.assertEqual(self.user.point_balance, 45)


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
