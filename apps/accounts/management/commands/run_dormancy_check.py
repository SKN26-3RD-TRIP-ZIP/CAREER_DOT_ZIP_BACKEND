"""
휴면 계정 감지 및 전환을 수동으로 실행하는 management command.

사용:
    python manage.py run_dormancy_check
    python manage.py run_dormancy_check --dry-run
    python manage.py run_dormancy_check --dormant-days 30 --warning-days 20  # 테스트용 기준 단축
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "미접속 계정의 휴면 예고 이메일 발송 및 휴면 전환을 실행한다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="실제 DB 변경 없이 대상 계정 목록만 출력한다.",
        )
        parser.add_argument(
            "--dormant-days",
            type=int,
            dest="dormant_days",
            default=None,
            help="휴면 전환 기준 일수 (기본값: 180). 테스트 시 단축 가능.",
        )
        parser.add_argument(
            "--warning-days",
            type=int,
            dest="warning_days",
            default=None,
            help="휴면 예고 기준 일수 (기본값: 150). 테스트 시 단축 가능.",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import User
        from apps.accounts.tasks import DORMANT_DAYS, WARNING_DAYS, _activity_date

        dry_run = options["dry_run"]
        dormant_days = options["dormant_days"] or DORMANT_DAYS
        warning_days = options["warning_days"] or WARNING_DAYS

        if options["dormant_days"] or options["warning_days"]:
            self.stdout.write(self.style.WARNING(
                f"[테스트 모드] 기준: 휴면={dormant_days}일, 예고={warning_days}일"
            ))
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] 실제 변경 없이 대상만 출력합니다."))

        from django.utils.timezone import localdate
        today = localdate()

        dormant_list = []
        warning_list = []

        for user in User.objects.filter(status="active"):
            activity = _activity_date(user)
            if activity is None:
                continue
            days_inactive = (today - activity.date()).days
            if days_inactive >= dormant_days:
                dormant_list.append((user, days_inactive))
            elif warning_days <= days_inactive < dormant_days:
                warning_list.append((user, days_inactive))

        self.stdout.write(f"\n[휴면 전환 대상] {len(dormant_list)}건")
        for user, days in dormant_list:
            self.stdout.write(f"  - {user.email} (마지막 활동: {_activity_date(user).date()}, {days}일 경과)")

        self.stdout.write(f"\n[휴면 예고 대상] {len(warning_list)}건")
        for user, days in warning_list:
            self.stdout.write(f"  - {user.email} (마지막 활동: {_activity_date(user).date()}, {days}일 경과)")

        if dry_run:
            return

        from apps.accounts.tasks import check_dormant_accounts
        result = check_dormant_accounts(dormant_days=dormant_days, warning_days=warning_days)

        self.stdout.write(self.style.SUCCESS(
            f"\n완료: 휴면 전환 {result['converted']}건, 예고 이메일 {result['warned']}건"
        ))
