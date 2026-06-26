from apps.accounts.management.commands.run_dormancy_check import Command as RunDormancyCheckCommand


class Command(RunDormancyCheckCommand):
    help = "미접속 계정을 휴면 상태로 전환한다. --dry-run으로 대상만 확인할 수 있다."
