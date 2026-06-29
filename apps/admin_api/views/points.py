from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from apps.accounts.models import PointHistory, PointPolicy, PointPolicyChangeLog
from apps.accounts.services.points import admin_adjust_points
from ..models import AuditLog
from ..serializers import (
    AdminPointAdjustSerializer,
    AdminPointHistoryQuerySerializer,
    AdminPointHistorySerializer,
    AdminPointPolicySerializer,
    AdminPointPolicyUpdateSerializer,
)
from .base import AdminAPIView, paginate

User = get_user_model()


class AdminPointAdjustView(AdminAPIView):
    def post(self, request, member_id):
        serializer = AdminPointAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = get_object_or_404(User, id=member_id)

        try:
            result = admin_adjust_points(
                user=member,
                amount=serializer.validated_data['amount'],
                reason=serializer.validated_data['reason'],
                actor_id=request.user.id,
                idempotency_key=serializer.validated_data.get('idempotency_key'),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.objects.create(
            actor=request.user,
            action_type='point_admin_adjust',
            target_type=User._meta.db_table,
            target_id=str(member.id),
            before_value={},
            after_value={
                'amount': result.history.amount,
                'balance_after': result.history.balance_after,
                'point_history_id': result.history.id,
                'created': result.created,
            },
        )

        return Response(
            {
                'point_history_id': result.history.id,
                'user_id': member.id,
                'amount': result.history.amount,
                'balance_after': result.history.balance_after,
                'created': result.created,
            },
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class AdminPointHistoryView(AdminAPIView):
    def get(self, request):
        query_serializer = AdminPointHistoryQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        histories = PointHistory.objects.select_related('user').order_by('-created_at', '-id')
        if params.get('user_id'):
            histories = histories.filter(user_id=params['user_id'])
        if params.get('transaction_type'):
            histories = histories.filter(transaction_type=params['transaction_type'])
        search = (params.get('search') or '').strip()
        if search:
            histories = histories.filter(
                Q(user__name__icontains=search) | Q(user__email__icontains=search)
            )

        total = histories.count()
        results = paginate(histories, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': AdminPointHistorySerializer(results, many=True).data,
            }
        )


class AdminPointPolicyListView(AdminAPIView):
    def get(self, request):
        policies = PointPolicy.objects.order_by('transaction_type', '-amount', 'reason_code')
        return Response({'results': AdminPointPolicySerializer(policies, many=True).data})


class AdminPointPolicyUpdateView(AdminAPIView):
    def patch(self, request, policy_id):
        serializer = AdminPointPolicyUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            policy = PointPolicy.objects.select_for_update().filter(id=policy_id).first()
            if policy is None:
                return Response({'detail': '정책을 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            new_amount = data.get('amount', policy.amount)
            # 부호 일관성 검증: 적립 정책은 양수, 차감 정책은 음수여야 적립/차감 로직이 깨지지 않는다.
            if policy.transaction_type == PointHistory.TRANSACTION_EARN and new_amount <= 0:
                return Response({'detail': '적립 정책 금액은 0보다 커야 합니다.'}, status=status.HTTP_400_BAD_REQUEST)
            if policy.transaction_type == PointHistory.TRANSACTION_USE and new_amount >= 0:
                return Response({'detail': '차감 정책 금액은 0보다 작아야 합니다.'}, status=status.HTTP_400_BAD_REQUEST)

            before = {'amount': policy.amount, 'is_active': policy.is_active}
            policy.amount = new_amount
            if 'is_active' in data:
                policy.is_active = data['is_active']
            policy.updated_by = request.user
            policy.save(update_fields=['amount', 'is_active', 'updated_by', 'updated_at'])
            after = {'amount': policy.amount, 'is_active': policy.is_active}

            # 정책 변경은 과거 적립분에 소급되지 않는다(PointHistory 는 불변). 변경 이력만 감사 기록한다.
            PointPolicyChangeLog.objects.create(
                policy=policy,
                actor=request.user,
                before_value=before,
                after_value=after,
                reason=data.get('reason', ''),
            )
            AuditLog.objects.create(
                actor=request.user,
                action_type='point_policy_update',
                target_type=PointPolicy._meta.db_table,
                target_id=str(policy.id),
                before_value=before,
                after_value=after,
            )

        return Response(AdminPointPolicySerializer(policy).data)
