from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.prompt.models import PersonaConfig
from .models import InterviewQuestion, InterviewSession
from .mvp_serializers import (
    MVPQuestionGenerateSerializer,
    MVPQuestionSerializer,
    MVPSessionCreateSerializer,
    MVPSessionStatusSerializer,
    STATUS_INPUT_MAP,
    serialize_mvp_session,
)
from .services.question_generator import generate_interview_questions


def get_prompt_version_id(session):
    persona = (
        PersonaConfig.objects.select_related('active_template__default_version')
        .filter(persona_type=session.persona, is_active=True)
        .first()
    )
    if persona and persona.active_template:
        return persona.active_template.default_version_id
    return None


class MVPSessionCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MVPSessionCreateSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(
            serialize_mvp_session(
                session,
                include_created_at=True,
                prompt_version_id=get_prompt_version_id(session),
            ),
            status=status.HTTP_201_CREATED,
        )


class MVPSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        return Response(serialize_mvp_session(session), status=status.HTTP_200_OK)


class MVPSessionStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, session_id):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        serializer = MVPSessionStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data['status']
        session.status = STATUS_INPUT_MAP[requested_status]
        if requested_status == 'in_progress' and session.started_at is None:
            session.started_at = timezone.now()
        if requested_status in {'completed', 'canceled', 'failed'} and session.ended_at is None:
            session.ended_at = timezone.now()
        session.save(update_fields=('status', 'started_at', 'ended_at', 'updated_at'))
        return Response(
            {
                'session_id': str(session.id),
                'status': requested_status,
                'ended_at': session.ended_at,
            },
            status=status.HTTP_200_OK,
        )


class MVPQuestionGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        serializer = MVPQuestionGenerateSerializer(
            data=request.data,
            context={'request': request, 'session': session},
        )
        serializer.is_valid(raise_exception=True)
        existing = session.questions.filter(question_type='main').order_by('order_index')
        if existing.exists():
            return self._response(existing)

        session.total_question_count = serializer.validated_data['question_count']
        session.save(update_fields=('total_question_count', 'updated_at'))
        created = [
            InterviewQuestion.objects.create(session=session, **question)
            for question in generate_interview_questions(session)
        ]
        return self._response(created)

    @staticmethod
    def _response(questions):
        serialized = MVPQuestionSerializer(questions, many=True).data
        return Response(
            {'generated_count': len(serialized), 'questions': serialized},
            status=status.HTTP_200_OK,
        )


class MVPQuestionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        questions = session.questions.filter(question_type='main').order_by('order_index')
        return Response(
            {
                'total': questions.count(),
                'results': MVPQuestionSerializer(questions, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
