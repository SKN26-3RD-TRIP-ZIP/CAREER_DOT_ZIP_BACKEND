from ..models import AuditLog


def record_audit(actor, action_type, target_type, target_id, before=None, after=None):
    """관리자 행위 감사 로그를 남기는 단일 헬퍼.

    여러 서비스에서 AuditLog.objects.create(...)를 직접 호출하던 중복을 제거한다.
    """
    return AuditLog.objects.create(
        actor=actor,
        action_type=action_type,
        target_type=target_type,
        target_id=str(target_id),
        before_value=before or {},
        after_value=after or {},
    )
