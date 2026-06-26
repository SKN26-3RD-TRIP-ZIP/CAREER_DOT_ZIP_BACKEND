from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from apps.accounts.models import PointHistory
from apps.accounts.services.points import admin_adjust_points
from ..models import AuditLog
from ..serializers import (
    AdminPointAdjustSerializer,
    AdminPointHistoryQuerySerializer,
    AdminPointHistorySerializer,
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
