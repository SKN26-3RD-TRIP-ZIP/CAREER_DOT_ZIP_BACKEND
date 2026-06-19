"""
회원 탈퇴(소프트 딜리트) 관련 테스트.

대상:
  - MemberDeleteView: 소프트 삭제 동작, 중복 탈퇴, 본인 탈퇴 차단
  - LoginSerializer: 탈퇴 계정 로그인 차단
  - cleanup_withdrawn_accounts: 보관 기간 경과 후 PII 익명화
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admin_api.models import AuditLog
from apps.accounts.tasks import cleanup_withdrawn_accounts

User = get_user_model()


class MemberWithdrawViewTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com', password='pass1234!', name='Admin', is_staff=True,
        )
        self.member = User.objects.create_user(
            email='member@example.com', password='pass1234!', name='홍길동',
        )
        self.client.force_authenticate(self.admin)

    def _delete(self, member_id):
        return self.client.delete(
            reverse('admin-member-detail', kwargs={'member_id': member_id})
        )

    # ── 정상 탈퇴 ──────────────────────────────────────────────────────────

    def test_withdraw_sets_status_and_withdrawn_at(self):
        response = self._delete(self.member.id)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, 'withdrawn')
        self.assertIsNotNone(self.member.withdrawn_at)
        self.assertFalse(self.member.is_active)

    def test_withdraw_preserves_user_data(self):
        """소프트 삭제 직후에는 이름·이메일이 원본 그대로 남아야 한다."""
        self._delete(self.member.id)

        self.member.refresh_from_db()
        self.assertEqual(self.member.email, 'member@example.com')
        self.assertEqual(self.member.name, '홍길동')

    def test_withdraw_creates_audit_log(self):
        self._delete(self.member.id)

        log = AuditLog.objects.get(action_type='member_withdraw')
        self.assertEqual(log.target_id, str(self.member.id))
        self.assertIn('email', log.before_value)
        self.assertIn('withdrawn_at', log.after_value)

    # ── 예외 케이스 ────────────────────────────────────────────────────────

    def test_cannot_withdraw_self(self):
        response = self._delete(self.admin.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_withdrawn_returns_400(self):
        self._delete(self.member.id)
        response = self._delete(self.member.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_admin_is_forbidden(self):
        other = User.objects.create_user(
            email='other@example.com', password='pass1234!', name='일반유저',
        )
        self.client.force_authenticate(other)

        response = self._delete(self.member.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class WithdrawnUserLoginTests(APITestCase):
    """탈퇴 계정은 로그인이 차단되어야 한다."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='bye@example.com', password='pass1234!', name='탈퇴자', is_verified=True,
        )
        self.user.status = 'withdrawn'
        self.user.withdrawn_at = timezone.now()
        self.user.is_active = False
        self.user.save()

    def test_withdrawn_user_cannot_login(self):
        response = self.client.post(
            reverse('login'),
            {'email': 'bye@example.com', 'password': 'pass1234!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CleanupWithdrawnAccountsTests(APITestCase):
    """보관 기간 경과 시 PII 익명화, 기간 내 계정은 보존."""

    def _make_withdrawn(self, email, days_ago):
        user = User.objects.create_user(
            email=email, password='pass1234!', name='테스트유저',
        )
        user.status = 'withdrawn'
        user.withdrawn_at = timezone.now() - timedelta(days=days_ago)
        user.is_active = False
        user.save()
        return user

    def test_anonymizes_expired_users(self):
        user = self._make_withdrawn('expired@example.com', days_ago=31)

        result = cleanup_withdrawn_accounts(retention_days=30)

        self.assertEqual(result['anonymized'], 1)
        user.refresh_from_db()
        self.assertTrue(user.email.startswith('withdrawn_'))
        self.assertEqual(user.name, '탈퇴회원')
        self.assertFalse(user.has_usable_password())

    def test_preserves_users_within_retention(self):
        user = self._make_withdrawn('recent@example.com', days_ago=10)

        result = cleanup_withdrawn_accounts(retention_days=30)

        self.assertEqual(result['anonymized'], 0)
        user.refresh_from_db()
        self.assertEqual(user.email, 'recent@example.com')

    def test_already_anonymized_users_are_skipped(self):
        """중복 실행해도 이미 익명화된 계정은 다시 처리하지 않는다."""
        user = self._make_withdrawn('skip@example.com', days_ago=60)
        cleanup_withdrawn_accounts(retention_days=30)

        result = cleanup_withdrawn_accounts(retention_days=30)

        self.assertEqual(result['anonymized'], 0)
        user.refresh_from_db()
        self.assertTrue(user.email.startswith('withdrawn_'))
