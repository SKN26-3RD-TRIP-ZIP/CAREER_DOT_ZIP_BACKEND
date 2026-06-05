from django.db.models import Count
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.interview.models import InterviewSession

from .serializers import InterviewHistoryQuerySerializer, InterviewHistorySerializer


class InterviewHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query_serializer = InterviewHistoryQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        limit = query_serializer.validated_data['limit']
        session_status = query_serializer.validated_data.get('status')

        sessions = (
            InterviewSession.objects.filter(user=request.user)
            .select_related('final_report')
            .annotate(
                question_count=Count('questions', distinct=True),
                answer_count=Count('answers', distinct=True),
            )
            .order_by('-created_at')
        )
        if session_status:
            sessions = sessions.filter(status=session_status)

        total = sessions.count()
        serializer = InterviewHistorySerializer(sessions[:limit], many=True)
        return Response(
            {
                'total': total,
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
