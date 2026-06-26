from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PointHistory, User


POLICY_VERSION = "2026.06"

POINT_POLICIES = {
    "AUTH.EMAIL_VERIFIED": 100,
    "PROFILE.COMPLETED": 500,
    "PROFILE.DESIRED_JOB_SET": 200,
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
