from __future__ import annotations

from dataclasses import dataclass

from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import PointHistory, PointPolicy, User


POLICY_VERSION = "2026.06"

POINT_POLICIES = {
    "AUTH.EMAIL_VERIFIED": 100,
    "PROFILE.COMPLETED": 500,
    "PROFILE.DESIRED_JOB_SET": 200,
    "JD.FIRST_CREATED": 500,
    "RESUME.FIRST_CREATED": 500,
    "COVER_LETTER.FIRST_CREATED": 500,
    "PROJECT.FIRST_CREATED": 500,
    "PROJECT.ADDITIONAL": 300,
    "LOGIN.DAILY": 50,
    "LOGIN.STREAK_7": 200,
    "LOGIN.STREAK_30": 100,
    "INTERVIEW.COMPLETED": 300,
    "REPORT.FIRST_VIEWED": 100,
    "ACTION_PLAN.CREATED": 200,
    "INTERVIEW.WEAKNESS_SESSION_COMPLETED": 300,
    "DORMANT.RETURN_LOGIN": 300,
    "INTERVIEW.SESSION_STARTED": -10,
    "INTERVIEW.EXTRA_SESSION": -100,
    "QUESTION_PACK.CUSTOM": -500,
    "PERSONA.ADVANCED": -300,
    "ANSWER.REEVALUATION": -400,
    "REPORT.DEEP_ANALYSIS": -800,
    "INTERVIEW.HINT": -300,
    "REPORT.GROWTH_COMPARE": -600,
    "PRACTICE.WEAKNESS_FOCUS": -500,
    "GITHUB.DEEP_ANALYSIS": -700,
    "ACTION_PLAN.REGENERATE": -300,
}

DAILY_ONCE_REASON_CODES = {
    "INTERVIEW.COMPLETED",
}


class InsufficientPointsError(ValueError):
    """Raised when a point debit would make the balance negative."""


@dataclass(frozen=True)
class PointTransactionResult:
    history: PointHistory
    created: bool


def _normalize_idempotency_key(idempotency_key: str | None) -> str | None:
    value = (idempotency_key or "").strip()
    return value or None


def _validate_amount(transaction_type: str, amount: int) -> None:
    if transaction_type in {PointHistory.TRANSACTION_EARN, PointHistory.TRANSACTION_REFUND} and amount <= 0:
        raise ValueError("Earn and refund transactions require a positive amount.")
    if transaction_type in {PointHistory.TRANSACTION_USE, PointHistory.TRANSACTION_EXPIRE} and amount >= 0:
        raise ValueError("Use and expire transactions require a negative amount.")
    if transaction_type == PointHistory.TRANSACTION_ADMIN and amount == 0:
        raise ValueError("Admin adjustment amount cannot be zero.")


def _default_policy_for(reason_code: str) -> dict:
    if reason_code not in POINT_POLICIES:
        raise ValueError(f"Unknown point policy: {reason_code}")
    amount = int(POINT_POLICIES[reason_code])
    if amount > 0:
        transaction_type = PointHistory.TRANSACTION_EARN
    elif amount < 0:
        transaction_type = PointHistory.TRANSACTION_USE
    else:
        raise ValueError("Point policy amount cannot be zero.")
    return {
        "reason_code": reason_code,
        "amount": amount,
        "transaction_type": transaction_type,
        "daily_limit": None,
        "monthly_limit": None,
        "account_once": reason_code in {
            "AUTH.EMAIL_VERIFIED",
            "PROFILE.COMPLETED",
            "PROFILE.DESIRED_JOB_SET",
            "JD.FIRST_CREATED",
            "RESUME.FIRST_CREATED",
            "COVER_LETTER.FIRST_CREATED",
            "PROJECT.FIRST_CREATED",
        },
        "per_reference_once": reason_code in {
            "INTERVIEW.COMPLETED",
            "REPORT.FIRST_VIEWED",
            "ACTION_PLAN.CREATED",
            "INTERVIEW.SESSION_STARTED",
            "QUESTION_PACK.CUSTOM",
            "REPORT.GROWTH_COMPARE",
            "PRACTICE.WEAKNESS_FOCUS",
            "GITHUB.DEEP_ANALYSIS",
        },
        "policy_version": POLICY_VERSION,
        "is_active": True,
    }


def resolve_point_policy(reason_code: str) -> dict:
    now = timezone.now()
    policy = (
        PointPolicy.objects
        .filter(reason_code=reason_code, is_active=True, effective_start_at__lte=now)
        .filter(models.Q(effective_end_at__isnull=True) | models.Q(effective_end_at__gt=now))
        .order_by('-effective_start_at', '-id')
        .first()
    )
    if policy is None:
        return _default_policy_for(reason_code)
    return {
        "reason_code": policy.reason_code,
        "amount": policy.amount,
        "transaction_type": policy.transaction_type,
        "daily_limit": policy.daily_limit,
        "monthly_limit": policy.monthly_limit,
        "account_once": policy.account_once,
        "per_reference_once": policy.per_reference_once,
        "policy_version": policy.policy_version,
        "is_active": policy.is_active,
    }


def _period_sum(*, user: User, reason_code: str, since, until) -> int:
    return (
        PointHistory.objects
        .filter(user=user, reason_code=reason_code, created_at__gte=since, created_at__lt=until)
        .aggregate(total=models.Sum('amount'))
        .get('total')
        or 0
    )


def _current_local_day_range():
    now = timezone.localtime(timezone.now())
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timezone.timedelta(days=1)
    return day_start, day_end


def _enforce_policy_limits(*, user: User, policy: dict, reference_id: str) -> None:
    reason_code = policy["reason_code"]
    amount = int(policy["amount"])
    if not policy.get("is_active"):
        raise ValueError(f"Point policy is inactive: {reason_code}")

    if policy.get("account_once") and PointHistory.objects.filter(user=user, reason_code=reason_code).exists():
        raise ValueError(f"Point policy can be applied only once per account: {reason_code}")

    if (
        policy.get("per_reference_once")
        and reference_id
        and PointHistory.objects.filter(user=user, reason_code=reason_code, reference_id=reference_id).exists()
    ):
        raise ValueError(f"Point policy can be applied only once per reference: {reason_code}")

    if amount <= 0:
        return

    day_start, day_end = _current_local_day_range()
    if (
        reason_code in DAILY_ONCE_REASON_CODES
        and PointHistory.objects.filter(
            user=user,
            reason_code=reason_code,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).exists()
    ):
        raise ValueError(f"Point policy can be applied only once per day: {reason_code}")

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    daily_limit = policy.get("daily_limit")
    if daily_limit is not None:
        if _period_sum(user=user, reason_code=reason_code, since=day_start, until=day_end) + amount > daily_limit:
            raise ValueError(f"Daily point policy limit exceeded: {reason_code}")

    monthly_limit = policy.get("monthly_limit")
    if monthly_limit is not None:
        if _period_sum(user=user, reason_code=reason_code, since=month_start, until=month_end) + amount > monthly_limit:
            raise ValueError(f"Monthly point policy limit exceeded: {reason_code}")


def _create_transaction(
    *,
    user: User,
    transaction_type: str,
    amount: int,
    reason_code: str,
    reference_id: str = "",
    idempotency_key: str | None = None,
    description: str = "",
    policy_version: str = POLICY_VERSION,
) -> PointTransactionResult:
    reason_code = (reason_code or "").strip()
    if not reason_code:
        raise ValueError("reason_code is required.")
    _validate_amount(transaction_type, amount)
    normalized_key = _normalize_idempotency_key(idempotency_key)

    with transaction.atomic():
        if normalized_key:
            existing = PointHistory.objects.select_related("user").filter(idempotency_key=normalized_key).first()
            if existing is not None:
                if existing.user_id != user.id:
                    raise ValueError("idempotency_key is already used by another user.")
                return PointTransactionResult(history=existing, created=False)

        locked_user = User.objects.select_for_update().get(pk=user.pk)
        next_balance = locked_user.point_balance + amount
        if next_balance < 0:
            raise InsufficientPointsError("Point balance is insufficient.")

        locked_user.point_balance = next_balance
        locked_user.point_last_updated_at = timezone.now()
        locked_user.save(update_fields=["point_balance", "point_last_updated_at", "updated_at"])

        history = PointHistory.objects.create(
            user=locked_user,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=next_balance,
            reason_code=reason_code,
            reference_id=(reference_id or ""),
            idempotency_key=normalized_key,
            policy_version=policy_version,
            description=description or "",
        )

    return PointTransactionResult(history=history, created=True)


def earn_points(
    *,
    user: User,
    amount: int,
    reason_code: str,
    reference_id: str = "",
    idempotency_key: str | None = None,
    description: str = "",
) -> PointTransactionResult:
    return _create_transaction(
        user=user,
        transaction_type=PointHistory.TRANSACTION_EARN,
        amount=abs(int(amount)),
        reason_code=reason_code,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        description=description,
    )


def use_points(
    *,
    user: User,
    amount: int,
    reason_code: str,
    reference_id: str = "",
    idempotency_key: str | None = None,
    description: str = "",
) -> PointTransactionResult:
    return _create_transaction(
        user=user,
        transaction_type=PointHistory.TRANSACTION_USE,
        amount=-abs(int(amount)),
        reason_code=reason_code,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        description=description,
    )


def refund_points(
    *,
    user: User,
    amount: int,
    reason_code: str,
    reference_id: str = "",
    idempotency_key: str | None = None,
    description: str = "",
) -> PointTransactionResult:
    return _create_transaction(
        user=user,
        transaction_type=PointHistory.TRANSACTION_REFUND,
        amount=abs(int(amount)),
        reason_code=reason_code,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        description=description,
    )


def apply_point_policy(
    *,
    user: User,
    reason_code: str,
    reference_id: str = "",
    idempotency_key: str | None = None,
    description: str = "",
) -> PointTransactionResult:
    policy = resolve_point_policy(reason_code)
    reference_id = reference_id or ""
    normalized_key = _normalize_idempotency_key(idempotency_key)
    if normalized_key:
        existing = PointHistory.objects.filter(idempotency_key=normalized_key).first()
        if existing is not None:
            if existing.user_id != user.id:
                raise ValueError("idempotency_key is already used by another user.")
            return PointTransactionResult(history=existing, created=False)

    _enforce_policy_limits(user=user, policy=policy, reference_id=reference_id)
    return _create_transaction(
        user=user,
        transaction_type=policy["transaction_type"],
        amount=policy["amount"],
        reason_code=reason_code,
        reference_id=reference_id,
        idempotency_key=normalized_key,
        description=description,
        policy_version=policy["policy_version"],
    )


def admin_adjust_points(
    *,
    user: User,
    amount: int,
    reason: str,
    actor_id: int | None = None,
    idempotency_key: str | None = None,
) -> PointTransactionResult:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Admin adjustment reason is required.")
    return _create_transaction(
        user=user,
        transaction_type=PointHistory.TRANSACTION_ADMIN,
        amount=int(amount),
        reason_code="ADMIN.ADJUSTMENT",
        idempotency_key=idempotency_key,
        description=f"actor_id={actor_id}; {reason}" if actor_id else reason,
    )
