from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.common.choices import INTERVIEW_SESSION_STATUS_COMPLETED

from .models import AuditLog
from .permissions import IsAdminUserOrRole
from .serializers import (
    AuditLogQuerySerializer,
    AuditLogSerializer,
    MemberListQuerySerializer,
    MemberListSerializer,
    MemberStatusSerializer,
)


User = get_user_model()


def paginate(queryset, page, size):
    start = (page - 1) * size
    return queryset[start:start + size]


class AdminAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserOrRole]


class MemberListView(AdminAPIView):
    def get(self, request):
        query_serializer = MemberListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        members = User.objects.annotate(
            practice_count=Count(
                'interview_sessions',
                filter=Q(interview_sessions__status=INTERVIEW_SESSION_STATUS_COMPLETED),
                distinct=True,
            )
        ).order_by('-created_at')
        if params.get('status'):
            members = members.filter(status=params['status'])

        total = members.count()
        results = paginate(members, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': MemberListSerializer(results, many=True).data,
            }
        )


class MemberStatusView(AdminAPIView):
    def patch(self, request, member_id):
        serializer = MemberStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        if request.user.id == member_id and new_status == 'suspended':
            return Response(
                {'detail': 'You cannot suspend your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            member = get_object_or_404(User.objects.select_for_update(), id=member_id)
            before_status = member.status
            member.status = new_status
            member.save(update_fields=('status', 'updated_at'))
            AuditLog.objects.create(
                actor=request.user,
                action_type='member_status_change',
                target_type=User._meta.db_table,
                target_id=str(member.id),
                before_value={'status': before_status},
                after_value={'status': member.status},
            )

        return Response(
            {
                'id': member.id,
                'status': member.status,
                'updated_at': member.updated_at,
            }
        )


class AuditLogListView(AdminAPIView):
    def get(self, request):
        query_serializer = AuditLogQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        audit_logs = AuditLog.objects.select_related('actor').order_by('-created_at')
        if params.get('action_type'):
            audit_logs = audit_logs.filter(action_type=params['action_type'])
        if params.get('actor_id'):
            audit_logs = audit_logs.filter(actor_id=params['actor_id'])

        total = audit_logs.count()
        results = paginate(audit_logs, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': AuditLogSerializer(results, many=True).data,
            }
        )
