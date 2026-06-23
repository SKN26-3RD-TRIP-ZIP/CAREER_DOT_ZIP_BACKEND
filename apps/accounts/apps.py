import os
import sys

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'Accounts'

    def ready(self):
        if not _should_start_scheduler():
            return

        _start_scheduler()


def _should_start_scheduler():
    argv0 = os.path.basename(sys.argv[0] or "")
    command = sys.argv[1] if len(sys.argv) > 1 else ""

    # Management commands initialize apps before scheduler tables may exist.
    if argv0 in {"manage.py", "django-admin", "django-admin.py"}:
        return command == "runserver" and os.environ.get("RUN_MAIN") == "true"

    # Multi-worker WSGI servers should opt in to one scheduler process.
    if "gunicorn" in argv0:
        return os.environ.get("ACCOUNTS_SCHEDULER_ENABLED") == "true"

    return True


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from django_apscheduler.jobstores import DjangoJobStore

    from .tasks import check_dormant_accounts, cleanup_withdrawn_accounts

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_jobstore(DjangoJobStore(), "default")
    scheduler.add_job(
        check_dormant_accounts,
        trigger=CronTrigger(hour=0, minute=0),
        id="check_dormant_accounts",
        name="Dormant account check and transition (daily 00:00)",
        jobstore="default",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        cleanup_withdrawn_accounts,
        trigger=CronTrigger(hour=0, minute=30),
        id="cleanup_withdrawn_accounts",
        name="Withdrawn account PII anonymization (daily 00:30)",
        jobstore="default",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
