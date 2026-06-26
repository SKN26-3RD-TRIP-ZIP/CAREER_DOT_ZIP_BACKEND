import uuid
from django.db import transaction
from django.utils import timezone

from apps.points.models import PointHistory


def _generate_idempotency_key(user_id: int, reason_code: str, reference_id=None) -> str:
    """reference_id가 없을 때 uuid 기반으로 자동 생성."""
    if reference_id is not None:
        return f"{reason_code}:{user_id}:{reference_id}"
    return f"{reason_code}:{user_id}:{uuid.uuid4().hex}"


@transaction.atomic
def award_points(
    user,
    amount: int,
    reason_code: str,
    reference_id=None,
    idempotency_key: str = None,
    expires_at=None,
) -> PointHistory:
    """
    포인트 적립.

    - amount는 양수여야 함.
    - idempotency_key를 직접 넘기면 중복 적립 방지에 사용됨.
      넘기지 않으면 reason_code + reference_id 조합으로 자동 생성.
    - 이미 처리된 key면 기존 이력을 그대로 반환 (멱등 보장).
    """
    if amount <= 0:
        raise ValueError(f"award_points: amount must be positive, got {amount}")

    key = idempotency_key or _generate_idempotency_key(user.id, reason_code, reference_id)

    existing = PointHistory.objects.filter(idempotency_key=key).first()
    if existing:
        return existing

    # select_for_update으로 동시 요청 시 잔액 꼬임 방지
    from django.contrib.auth import get_user_model
    User = get_user_model()
    locked_user = User.objects.select_for_update().get(pk=user.pk)

    locked_user.point_balance += amount
    locked_user.save(update_fields=['point_balance', 'updated_at'])

    return PointHistory.objects.create(
        user=locked_user,
        amount=amount,
        reason_code=reason_code,
        reference_id=reference_id,
        idempotency_key=key,
        balance_after=locked_user.point_balance,
        expires_at=expires_at,
    )


@transaction.atomic
def deduct_points(
    user,
    amount: int,
    reason_code: str,
    reference_id=None,
    idempotency_key: str = None,
) -> PointHistory:
    """
    포인트 차감.

    - amount는 양수로 넘기면 내부에서 음수로 저장.
    - 잔액 부족 시 ValueError 발생.
    - 이미 처리된 key면 기존 이력을 그대로 반환 (멱등 보장).
    """
    if amount <= 0:
        raise ValueError(f"deduct_points: amount must be positive, got {amount}")

    key = idempotency_key or _generate_idempotency_key(user.id, reason_code, reference_id)

    existing = PointHistory.objects.filter(idempotency_key=key).first()
    if existing:
        return existing

    from django.contrib.auth import get_user_model
    User = get_user_model()
    locked_user = User.objects.select_for_update().get(pk=user.pk)

    if locked_user.point_balance < amount:
        raise ValueError(
            f"잔액 부족: 보유 {locked_user.point_balance}P, 차감 요청 {amount}P"
        )

    locked_user.point_balance -= amount
    locked_user.save(update_fields=['point_balance', 'updated_at'])

    return PointHistory.objects.create(
        user=locked_user,
        amount=-amount,
        reason_code=reason_code,
        reference_id=reference_id,
        idempotency_key=key,
        balance_after=locked_user.point_balance,
        expires_at=None,
    )
