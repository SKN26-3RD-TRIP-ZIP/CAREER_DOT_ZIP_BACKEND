"""
휴면 계정 감지 및 전환 스케줄 작업.

실행 방식:
  - APScheduler(django-apscheduler)가 매일 00:00(KST)에 자동 실행.
  - 수동 실행: python manage.py run_dormancy_check

휴면 정책:
  - 150일 미접속: 예고 이메일 발송 (30일 후 휴면 전환 예정 안내)
  - 180일 미접속: 즉시 status='dormant' 전환 + 휴면 전환 이메일 발송

기준 필드:
  - last_login: SimpleJWT가 로그인 성공 시 자동 갱신 (UPDATE_LAST_LOGIN=True)
  - 단, last_login이 None인 유저(가입 후 한 번도 로그인 안 함)는
    created_at 기준으로 판단한다.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger("apps.accounts")

DORMANT_DAYS = 180
WARNING_DAYS = 150
WITHDRAWAL_RETENTION_DAYS = 30


def _activity_date(user):
    """last_login이 없으면 created_at을 활동 기준으로 사용한다."""
    return user.last_login or user.created_at


def check_dormant_accounts(dormant_days: int = DORMANT_DAYS, warning_days: int = WARNING_DAYS):
    """
    휴면 예고 및 휴면 전환을 처리한다.
    APScheduler 또는 management command에서 호출한다.
    dormant_days/warning_days는 테스트 시 단축 기준으로 덮어쓸 수 있다.

    날짜(date)만 비교해 시각 차이로 인한 경계값 누락을 방지한다.
    예고 이메일은 warning_days째 되는 날 하루만 발송한다.
    """
    from django.utils.timezone import localdate

    from .emails import send_dormancy_warning_email, send_dormancy_email
    from .models import User

    today = localdate()
    converted = 0
    warned = 0

    for user in User.objects.filter(status="active"):
        activity = _activity_date(user)
        if activity is None:
            continue

        activity_date = activity.date()
        days_inactive = (today - activity_date).days

        if days_inactive >= dormant_days:
            try:
                send_dormancy_email(user)
            except Exception:
                logger.exception("휴면 전환 이메일 발송 실패 user_id=%s", user.id)
            user.status = "dormant"
            user.save(update_fields=["status", "updated_at"])
            converted += 1
            logger.info("휴면 전환 user_id=%s last_activity=%s days=%d", user.id, activity_date, days_inactive)

        elif warning_days <= days_inactive < dormant_days:
            if user.dormancy_warning_sent_at is not None:
                continue
            try:
                send_dormancy_warning_email(user)
                user.dormancy_warning_sent_at = timezone.now()
                user.save(update_fields=["dormancy_warning_sent_at", "updated_at"])
                warned += 1
                logger.info("휴면 예고 이메일 발송 user_id=%s last_activity=%s days=%d", user.id, activity_date, days_inactive)
            except Exception:
                logger.exception("휴면 예고 이메일 발송 실패 user_id=%s", user.id)

    logger.info("휴면 처리 완료: 전환=%d건, 예고=%d건", converted, warned)
    return {"converted": converted, "warned": warned}


def cleanup_withdrawn_accounts(retention_days: int = WITHDRAWAL_RETENTION_DAYS):
    """탈퇴 후 보관 기간이 지난 계정의 개인정보를 익명화한다.

    APScheduler 또는 management command(run_withdrawal_cleanup)에서 호출한다.
    retention_days는 테스트 시 단축 기준으로 덮어쓸 수 있다.

    대상: status='withdrawn' 이고 withdrawn_at 이 보관 기간을 초과한 계정.
    이미 익명화된 계정(email이 'withdrawn_'로 시작)은 중복 처리하지 않는다.
    익명화 내용: email→'withdrawn_<id>@deleted.invalid', name→'탈퇴회원',
    비밀번호 무효화.
    """
    from .models import User

    cutoff = timezone.now() - timedelta(days=retention_days)
    targets = User.objects.filter(
        status="withdrawn", withdrawn_at__lte=cutoff
    ).exclude(email__startswith="withdrawn_")

    anonymized = 0
    for user in targets:
        user.email = f"withdrawn_{user.id}@deleted.invalid"
        user.name = "탈퇴회원"
        user.set_unusable_password()
        user.save(update_fields=["email", "name", "password", "updated_at"])
        anonymized += 1
        logger.info("탈퇴 계정 익명화 user_id=%s", user.id)

    logger.info("탈퇴 익명화 완료: %d건", anonymized)
    return {"anonymized": anonymized}
