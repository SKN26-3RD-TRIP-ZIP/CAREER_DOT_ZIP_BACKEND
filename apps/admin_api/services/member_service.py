from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .audit import record_audit

User = get_user_model()


def withdraw_member(member_id, actor):
    """회원을 소프트 삭제(탈퇴 처리)한다.

    상태만 'withdrawn'으로 바꾸고 개인정보는 보관 기간 경과 후
    cleanup_withdrawn_accounts 배치에서 익명화한다.

    이미 탈퇴한 회원이면 아무 작업도 하지 않고 None을 반환하고,
    그 외에는 탈퇴 처리된 회원 인스턴스를 반환한다.
    """
    with transaction.atomic():
        member = get_object_or_404(User.objects.select_for_update(), id=member_id)
        if member.status == 'withdrawn':
            return None

        before = {'email': member.email, 'name': member.name, 'status': member.status}

        member.status = 'withdrawn'
        member.withdrawn_at = timezone.now()
        member.is_active = False
        member.save(update_fields=['status', 'withdrawn_at', 'is_active', 'updated_at'])

        record_audit(
            actor, 'member_withdraw', User._meta.db_table, member.id,
            before=before,
            after={'status': 'withdrawn', 'withdrawn_at': member.withdrawn_at.isoformat()},
        )
    return member


def change_member_status(member_id, new_status, actor):
    """회원 상태(active/dormant/banned 등)를 변경하고 감사 로그를 남긴다."""
    with transaction.atomic():
        member = get_object_or_404(User.objects.select_for_update(), id=member_id)
        before_status = member.status
        member.status = new_status
        member.save(update_fields=('status', 'updated_at'))
        record_audit(
            actor, 'member_status_change', User._meta.db_table, member.id,
            before={'status': before_status},
            after={'status': member.status},
        )
    return member


def invite_or_reactivate_member(email, actor):
    """이메일로 회원을 초대하거나, 차단된 계정을 재활성화한다.

    반환: (kind, member)
      - 'reactivated' : 차단 계정을 active로 되돌림 (member 반환)
      - 'invited'     : 신규 초대 처리 (member=None)
      - 'conflict'    : 이미 활성 상태인 계정이라 처리 불가 (member 반환)
    """
    existing = User.objects.filter(email=email).first()
    if existing:
        if existing.status != 'banned':
            return 'conflict', existing
        with transaction.atomic():
            before_status = existing.status
            existing.status = 'active'
            existing.is_verified = False
            existing.save(update_fields=('status', 'is_verified', 'updated_at'))
            record_audit(
                actor, 'member_invite_reactivate', User._meta.db_table, existing.id,
                before={'status': before_status},
                after={'status': 'active', 'is_verified': False},
            )
        return 'reactivated', existing

    record_audit(
        actor, 'member_invite_new', 'email', email,
        after={'invited_email': email},
    )
    return 'invited', None
