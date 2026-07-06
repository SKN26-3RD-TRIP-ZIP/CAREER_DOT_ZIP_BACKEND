from rest_framework.response import Response

from apps.interview.models import GuardrailEvent
from ..serializers import AdminGuardrailEventQuerySerializer, AdminGuardrailEventSerializer
from .base import AdminAPIView, paginate


class AdminGuardrailEventListView(AdminAPIView):
    def get(self, request):
        query_serializer = AdminGuardrailEventQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        events = GuardrailEvent.objects.select_related(
            'user',
            'session',
            'question',
            'answer',
        ).order_by('-created_at', '-id')
        if params.get('category'):
            events = events.filter(category=params['category'])
        if params.get('action'):
            events = events.filter(action=params['action'])
        if params.get('user_id'):
            events = events.filter(user_id=params['user_id'])
        if params.get('session_id'):
            events = events.filter(session_id=params['session_id'])

        total = events.count()
        results = paginate(events, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': AdminGuardrailEventSerializer(results, many=True).data,
            }
        )
