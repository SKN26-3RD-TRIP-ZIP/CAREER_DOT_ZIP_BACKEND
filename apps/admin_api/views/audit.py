from rest_framework.response import Response

from ..models import AuditLog
from ..serializers import AuditLogQuerySerializer, AuditLogSerializer
from .base import AdminAPIView, paginate


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
        return Response({
            'total': total,
            'page': params['page'],
            'size': params['size'],
            'results': AuditLogSerializer(results, many=True).data,
        })
