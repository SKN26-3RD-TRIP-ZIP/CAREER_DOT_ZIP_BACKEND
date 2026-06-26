from apps.accounts.models import PointHistory
from apps.accounts.services.points import earn_points, use_points


def _reference_to_string(reference_id=None) -> str:
    return '' if reference_id is None else str(reference_id)


def award_points(
    user,
    amount: int,
    reason_code: str,
    reference_id=None,
    idempotency_key: str = None,
    expires_at=None,
) -> PointHistory:
    if amount <= 0:
        raise ValueError(f'award_points: amount must be positive, got {amount}')

    result = earn_points(
        user=user,
        amount=amount,
        reason_code=reason_code,
        reference_id=_reference_to_string(reference_id),
        idempotency_key=idempotency_key,
        description='expires_at={}'.format(expires_at.isoformat()) if expires_at else '',
    )
    return result.history


def deduct_points(
    user,
    amount: int,
    reason_code: str,
    reference_id=None,
    idempotency_key: str = None,
) -> PointHistory:
    if amount <= 0:
        raise ValueError(f'deduct_points: amount must be positive, got {amount}')

    result = use_points(
        user=user,
        amount=amount,
        reason_code=reason_code,
        reference_id=_reference_to_string(reference_id),
        idempotency_key=idempotency_key,
    )
    return result.history
