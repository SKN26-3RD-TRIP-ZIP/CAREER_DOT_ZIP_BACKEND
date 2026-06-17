import os

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'Accounts'

    def ready(self):
        # management command, test, migrate 실행 시에는 스케줄러를 시작하지 않는다.
        import sys
        skip_cmds = {"migrate", "makemigrations", "test", "shell", "run_dormancy_check", "seed_qa_users"}
        if any(cmd in sys.argv for cmd in skip_cmds):
            return

        # 워커 프로세스가 여러 개일 때 중복 실행 방지 (gunicorn --workers>1 환경)
        if os.environ.get("RUN_MAIN") == "true" or "gunicorn" not in sys.argv[0]:
            _start_scheduler()


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from django_apscheduler.jobstores import DjangoJobStore

    from .tasks import check_dormant_accounts

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_jobstore(DjangoJobStore(), "default")
    scheduler.add_job(
        check_dormant_accounts,
        trigger=CronTrigger(hour=0, minute=0),
        id="check_dormant_accounts",
        name="휴면 계정 감지 및 전환 (매일 00:00)",
        jobstore="default",
        replace_existing=True,
        misfire_grace_time=3600,  # 서버 재시작 등으로 1시간 내 실행 못 한 경우 보정
    )
    scheduler.start()
