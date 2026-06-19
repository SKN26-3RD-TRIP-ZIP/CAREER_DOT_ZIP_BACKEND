"""
탈퇴 계정 개인정보 익명화를 수동으로 실행하는 management command.

사용:
    python manage.py run_withdrawal_cleanup
    python manage.py run_withdrawal_cleanup --dry-run
    python manage.py run_withdrawal_cleanup --retention-days 7  # 테스트용 단축
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "탈퇴 후 보관 기간이 지난 계정의 개인정보를 익명화한다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="실제 변경 없이 대상 계정 목록만 출력한다.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            dest="retention_days",
            default=None,
            help="개인정보 보관 기간 (기본값: 30일).",
        )

    def handle(self, *args, **options):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import User
        from apps.accounts.tasks import WITHDRAWAL_RETENTION_DAYS

        retention_days = options["retention_days"] or WITHDRAWAL_RETENTION_DAYS
        dry_run = options["dry_run"]

        if options["retention_days"]:
            self.stdout.write(self.style.WARNING(f"[테스트 모드] 보관 기간: {retention_days}일"))
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] 실제 변경 없이 대상만 출력합니다."))

        cutoff = timezone.now() - timedelta(days=retention_days)
        targets = User.objects.filter(status='withdrawn', withdrawn_at__lte=cutoff).exclude(
            email__startswith='withdrawn_'
        )

        self.stdout.write(f"\n[익명화 대상] {targets.count()}건")
        for user in targets:
            self.stdout.write(f"  - id={user.id} {user.email} (탈퇴일: {user.withdrawn_at.date()})")

        if dry_run:       
            return

        from apps.accounts.tasks import cleanup_withdrawn_accounts
        result = cleanup_withdrawn_accounts(retention_days=retention_days)
        self.stdout.write(self.style.SUCCESS(f"\n완료: 익명화 {result['anonymized']}건"))
