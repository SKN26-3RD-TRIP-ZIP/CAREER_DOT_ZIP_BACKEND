"""
휴면/탈퇴 배치 작업 테스트.

대상:
  - check_dormant_accounts (apps.accounts.tasks): 휴면 전환·예고 로직
  - run_dormancy_check / mark_dormant_accounts management command
  - run_withdrawal_cleanup management command

원칙:
  - 이메일 발송은 mock 처리하여 SMTP 의존성과 부수효과를 제거한다.
  - 미접속 기간은 last_login 필드를 직접 세팅해 시뮬레이션한다.
    (_activity_date는 last_login or created_at을 기준으로 삼고,
     created_at/updated_at은 auto 필드라 직접 설정할 수 없다.)
  - cleanup_withdrawn_accounts 함수 자체는 test_member_withdraw.py에서
    이미 검증하므로, 여기서는 커맨드 계층(dry-run·기준 override)에 집중한다.
"""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.tasks import DORMANT_DAYS, WARNING_DAYS, check_dormant_accounts

User = get_user_model()


def _make_user(email, *, days_inactive=None, status="active", **extra):
    """테스트용 유저 생성. days_inactive만큼 과거에 마지막 로그인한 것으로 세팅."""
    user = User.objects.create_user(
        email=email, password="pass1234!", name="테스트유저", **extra
    )
    if days_inactive is not None:
        user.last_login = timezone.now() - timedelta(days=days_inactive)
    if status != "active":
        user.status = status
    user.save()
    return user


class DormancyEmailMockMixin:
    """휴면 관련 이메일 발송을 mock 처리한다.

    tasks.check_dormant_accounts는 호출 시점에 apps.accounts.emails에서
    import하므로 원본 모듈 속성을 패치한다.
    """

    def setUp(self):
        super().setUp()
        p_convert = mock.patch("apps.accounts.emails.send_dormancy_email")
        p_warn = mock.patch("apps.accounts.emails.send_dormancy_warning_email")
        self.mock_dormancy_email = p_convert.start()
        self.mock_warning_email = p_warn.start()
        self.addCleanup(p_convert.stop)
        self.addCleanup(p_warn.stop)


# ── check_dormant_accounts 로직 ────────────────────────────────────────────


class CheckDormantAccountsTests(DormancyEmailMockMixin, TestCase):
    def test_converts_user_over_dormant_threshold(self):
        user = _make_user("old@example.com", days_inactive=DORMANT_DAYS + 10)

        result = check_dormant_accounts()

        self.assertEqual(result["converted"], 1)
        self.assertEqual(result["warned"], 0)
        user.refresh_from_db()
        self.assertEqual(user.status, "dormant")
        self.mock_dormancy_email.assert_called_once_with(user)

    def test_warns_user_in_warning_window(self):
        # 150 <= days < 180 → 예고만, 전환은 아님
        user = _make_user("warn@example.com", days_inactive=WARNING_DAYS + 5)

        result = check_dormant_accounts()

        self.assertEqual(result["converted"], 0)
        self.assertEqual(result["warned"], 1)
        user.refresh_from_db()
        self.assertEqual(user.status, "active")
        self.assertIsNotNone(user.dormancy_warning_sent_at)
        self.mock_warning_email.assert_called_once_with(user)

    def test_warning_not_resent_when_already_sent(self):
        user = _make_user("warned@example.com", days_inactive=WARNING_DAYS + 5)
        user.dormancy_warning_sent_at = timezone.now()
        user.save(update_fields=["dormancy_warning_sent_at"])

        result = check_dormant_accounts()

        self.assertEqual(result["warned"], 0)
        self.mock_warning_email.assert_not_called()

    def test_recent_user_untouched(self):
        user = _make_user("recent@example.com", days_inactive=10)

        result = check_dormant_accounts()

        self.assertEqual(result, {"converted": 0, "warned": 0})
        user.refresh_from_db()
        self.assertEqual(user.status, "active")
        self.mock_dormancy_email.assert_not_called()
        self.mock_warning_email.assert_not_called()

    def test_non_active_users_are_ignored(self):
        """이미 dormant/withdrawn 상태면 미접속 기간과 무관하게 건너뛴다."""
        _make_user("already@example.com", days_inactive=DORMANT_DAYS + 100, status="dormant")

        result = check_dormant_accounts()

        self.assertEqual(result, {"converted": 0, "warned": 0})
        self.mock_dormancy_email.assert_not_called()

    def test_custom_thresholds(self):
        """단축 기준으로 전환·예고 경계가 함께 이동한다."""
        convert_target = _make_user("c@example.com", days_inactive=35)
        warn_target = _make_user("w@example.com", days_inactive=25)
        safe = _make_user("s@example.com", days_inactive=10)

        result = check_dormant_accounts(dormant_days=30, warning_days=20)

        self.assertEqual(result["converted"], 1)
        self.assertEqual(result["warned"], 1)
        convert_target.refresh_from_db()
        warn_target.refresh_from_db()
        safe.refresh_from_db()
        self.assertEqual(convert_target.status, "dormant")
        self.assertEqual(warn_target.status, "active")
        self.assertIsNotNone(warn_target.dormancy_warning_sent_at)
        self.assertEqual(safe.status, "active")

    def test_conversion_survives_email_failure(self):
        """전환 이메일 발송이 실패해도 상태 전환은 진행된다."""
        self.mock_dormancy_email.side_effect = RuntimeError("SMTP down")
        user = _make_user("resilient@example.com", days_inactive=DORMANT_DAYS + 1)

        result = check_dormant_accounts()

        self.assertEqual(result["converted"], 1)
        user.refresh_from_db()
        self.assertEqual(user.status, "dormant")


# ── run_dormancy_check / mark_dormant_accounts 커맨드 ───────────────────────


class RunDormancyCheckCommandTests(DormancyEmailMockMixin, TestCase):
    def _call(self, command="run_dormancy_check", **opts):
        out = StringIO()
        call_command(command, stdout=out, **opts)
        return out.getvalue()

    def test_dry_run_makes_no_changes(self):
        user = _make_user("dry@example.com", days_inactive=DORMANT_DAYS + 10)

        output = self._call(dry_run=True)

        user.refresh_from_db()
        self.assertEqual(user.status, "active")
        self.mock_dormancy_email.assert_not_called()
        self.assertIn("DRY RUN", output)
        self.assertIn("휴면 전환 대상", output)

    def test_executes_conversion(self):
        user = _make_user("do@example.com", days_inactive=DORMANT_DAYS + 10)

        output = self._call()

        user.refresh_from_db()
        self.assertEqual(user.status, "dormant")
        self.assertIn("완료", output)

    def test_mark_dormant_accounts_alias_behaves_same(self):
        """mark_dormant_accounts는 run_dormancy_check의 서브클래스."""
        user = _make_user("alias@example.com", days_inactive=DORMANT_DAYS + 10)

        self._call(command="mark_dormant_accounts")

        user.refresh_from_db()
        self.assertEqual(user.status, "dormant")

    def test_custom_thresholds_via_options(self):
        user = _make_user("opt@example.com", days_inactive=35)

        output = self._call(dormant_days=30, warning_days=20)

        user.refresh_from_db()
        self.assertEqual(user.status, "dormant")
        self.assertIn("테스트 모드", output)


# ── run_withdrawal_cleanup 커맨드 ──────────────────────────────────────────


class RunWithdrawalCleanupCommandTests(TestCase):
    def _make_withdrawn(self, email, days_ago):
        user = User.objects.create_user(
            email=email, password="pass1234!", name="탈퇴유저",
        )
        user.status = "withdrawn"
        user.withdrawn_at = timezone.now() - timedelta(days=days_ago)
        user.is_active = False
        user.save()
        return user

    def _call(self, **opts):
        out = StringIO()
        call_command("run_withdrawal_cleanup", stdout=out, **opts)
        return out.getvalue()

    def test_dry_run_makes_no_changes(self):
        user = self._make_withdrawn("dry@example.com", days_ago=40)

        output = self._call(dry_run=True, retention_days=30)

        user.refresh_from_db()
        self.assertEqual(user.email, "dry@example.com")
        self.assertIn("DRY RUN", output)
        self.assertIn("익명화 대상", output)

    def test_executes_anonymization(self):
        user = self._make_withdrawn("expired@example.com", days_ago=40)

        output = self._call(retention_days=30)

        user.refresh_from_db()
        self.assertTrue(user.email.startswith("withdrawn_"))
        self.assertEqual(user.name, "탈퇴회원")
        self.assertFalse(user.has_usable_password())
        self.assertIn("완료", output)

    def test_within_retention_preserved(self):
        user = self._make_withdrawn("recent@example.com", days_ago=10)

        self._call(retention_days=30)

        user.refresh_from_db()
        self.assertEqual(user.email, "recent@example.com")
