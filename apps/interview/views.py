from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InterviewSession
from .serializers import (
    InterviewSessionCreateSerializer,
    InterviewSessionListSerializer,
    InterviewSessionDetailSerializer,
    InterviewSessionStatusSerializer,
)
from .models import InterviewQuestion
from .serializers import InterviewQuestionSerializer
from .services.question_generator import generate_interview_questions


class InterviewSessionListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return InterviewSession.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InterviewSessionCreateSerializer
        return InterviewSessionListSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        session = serializer.instance
        return Response(
            {
                'session_id': str(session.id),
                'interview_type': session.interview_type,
                'persona': session.persona,
                'status': session.status,
                'total_question_count': session.total_question_count,
                'created_at': session.created_at,
            },
            status=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = InterviewSessionListSerializer(queryset, many=True)
        return Response(
            {
                'total': queryset.count(),
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class InterviewSessionDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InterviewSessionDetailSerializer
    lookup_field = 'id'
    lookup_url_kwarg = 'session_id'

    def get_queryset(self):
        return InterviewSession.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class InterviewSessionStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return InterviewSession.objects.get(id=self.kwargs['session_id'], user=self.request.user)

    def patch(self, request, session_id):
        session = self.get_object()
        serializer = InterviewSessionStatusSerializer(session, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data.get('status')

        if new_status == 'in_progress' and session.started_at is None:
            session.started_at = timezone.now()
        if new_status in ['completed', 'cancelled'] and session.ended_at is None:
            session.ended_at = timezone.now()

        session.status = new_status
        session.save()

        return Response(
            {
                'session_id': str(session.id),
                'status': session.status,
                'updated_at': session.updated_at,
            },
            status=status.HTTP_200_OK,
        )


class InterviewQuestionGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_session(self, session_id):
        try:
            return InterviewSession.objects.get(id=session_id, user=self.request.user)
        except InterviewSession.DoesNotExist:
            return None

    def post(self, request, session_id):
        session = self.get_session(session_id)
        if not session:
            return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

        force = request.data.get('force_regenerate', False)
        existing_qs = session.questions.all()
        if existing_qs.exists() and not force:
            serializer = InterviewQuestionSerializer(existing_qs, many=True)
            return Response({'session_id': str(session.id), 'total': existing_qs.count(), 'questions': serializer.data}, status=status.HTTP_200_OK)

        # delete existing if force
        if force:
            existing_qs.delete()

        # generate deterministic questions via service
        generated = generate_interview_questions(session)

        created = []
        for q in generated:
            iq = InterviewQuestion.objects.create(
                session=session,
                order_index=q.get('order_index'),
                question_type=q.get('question_type'),
                question_text=q.get('question_text'),
                source_type=q.get('source_type'),
                source_reference=q.get('source_reference'),
            )
            created.append(iq)

        serializer = InterviewQuestionSerializer(created, many=True)
        return Response({'session_id': str(session.id), 'total': len(created), 'questions': serializer.data}, status=status.HTTP_201_CREATED)


class InterviewQuestionListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InterviewQuestionSerializer

    def get_queryset(self):
        session_id = self.kwargs.get('session_id')
        return InterviewQuestion.objects.filter(session__id=session_id, session__user=self.request.user).order_by('order_index')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({'session_id': kwargs.get('session_id'), 'total': queryset.count(), 'results': serializer.data}, status=status.HTTP_200_OK)
