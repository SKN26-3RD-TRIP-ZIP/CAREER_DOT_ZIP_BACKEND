from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from rest_framework import parsers
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.prompt.models import PersonaConfig
from .models import InterviewAnswer, InterviewQuestion, InterviewSession, QuestionSourceTag
from .mvp_serializers import (
    MVPQuestionGenerateSerializer,
    MVPQuestionSerializer,
    MVPAnswerCreateSerializer,
    MVPSTTResultUpdateSerializer,
    MVPFollowupQuestionSerializer,
    MVPSessionCreateSerializer,
    MVPSessionStatusSerializer,
    STATUS_INPUT_MAP,
    serialize_mvp_session,
)
from .services.question_generator import generate_interview_questions
from .services.answer_service import AnswerService
from .services.follow_up_generator import FollowupGenerator
from .services.whisper_stt_service import transcribe_uploaded_audio
from .services.ai_chain_openai_engine import AIChainOpenAIError


def get_prompt_version_id(session):
    persona = (
        PersonaConfig.objects.select_related('active_template__default_version')
        .filter(persona_type=session.persona, is_active=True)
        .first()
    )
    if persona and persona.active_template:
        return persona.active_template.default_version_id
    return None


def ai_generation_failed_response(*, detail, code, exc=None, http_status=status.HTTP_502_BAD_GATEWAY):
    data = {
        'detail': detail,
        'code': code,
        'error_code': code,
        'retryable': True,
    }
    chain_name = getattr(exc, 'chain_name', None)
    if chain_name:
        data['chain'] = chain_name
    return Response(data, status=http_status)


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


def _save_question_source_tags(question, source_tags):
    source_tag_objects = []

    for tag in source_tags or []:
        if not isinstance(tag, dict):
            continue

        source_tag_objects.append(
            QuestionSourceTag(
                question=question,
                source_type=tag.get('source_type') or question.source_type or 'general',
                source_label=tag.get('source_label') or '',
                source_text_excerpt=tag.get('source_text_excerpt') or '',
                source_reference=tag.get('source_reference') or question.source_reference or '',
            )
        )

    if source_tag_objects:
        QuestionSourceTag.objects.bulk_create(source_tag_objects)


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

        try:
            generated = generate_interview_questions(session)
        except AIChainOpenAIError as exc:
            return ai_generation_failed_response(
                detail='질문 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.',
                code='AI_QUESTION_GENERATION_FAILED',
                exc=exc,
            )
        created = []

        for question in generated:
            source_tags = question.get('source_tags', [])

            interview_question = InterviewQuestion.objects.create(
                session=session,
                question_text=question.get('question_text'),
                question_type=question.get('question_type', 'main'),
                order_index=question.get('order_index'),
                difficulty=question.get('difficulty'),
                source_type=question.get('source_type', 'general'),
                source_reference=question.get('source_reference'),
            )
            _save_question_source_tags(interview_question, source_tags)
            created.append(interview_question)

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


class MVPAnswerCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MVPAnswerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answer = AnswerService.create_answer(
            user=request.user,
            session_id=serializer.validated_data['session_id'],
            question_id=serializer.validated_data['question_id'],
            answer_text=serializer.validated_data['answer_text'],
            speech_duration=serializer.validated_data.get('speech_duration'),
        )
        return Response(
            {
                'answer_id': str(answer.id),
                'created_at': answer.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class MVPSTTResultUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, answer_id):
        answer = get_object_or_404(
            InterviewAnswer.objects.select_related('session', 'question'),
            id=answer_id,
            session__user=request.user,
        )
        serializer = MVPSTTResultUpdateSerializer(
            answer,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(
            answer_text=serializer.validated_data['stt_text'],
            answer_source='stt',
        )
        return Response(
            {
                'answer_id': str(answer.id),
                'stt_text': answer.stt_text,
                'updated_at': answer.updated_at,
            },
            status=status.HTTP_200_OK,
        )


class MVPWhisperTranscribeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        audio_file = request.FILES.get('audio')
        language = request.data.get('language') or 'ko'
        result = transcribe_uploaded_audio(audio_file, language=language)
        return Response(result, status=status.HTTP_200_OK)


class MVPWhisperDevTranscribeView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        if not settings.DEBUG:
            return Response(
                {'detail': 'Development STT endpoint is disabled.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        audio_file = request.FILES.get('audio')
        language = request.data.get('language') or 'ko'
        result = transcribe_uploaded_audio(audio_file, language=language)
        return Response(result, status=status.HTTP_200_OK)


class MVPFollowupQuestionCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, answer_id):
        answer = AnswerService.get_owned_answer(answer_id=answer_id, user=request.user)

        try:
            followup, created = FollowupGenerator.create_followup(answer)
        except AIChainOpenAIError as exc:
            return ai_generation_failed_response(
                detail='꼬리질문 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.',
                code='AI_FOLLOWUP_GENERATION_FAILED',
                exc=exc,
            )

        if followup is None:
            return Response(
                {
                    'answer_id': str(answer.id),
                    'next_action': 'NEXT_QUESTION',
                    'followup_question': None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                'answer_id': str(answer.id),
                'next_action': 'GENERATE_FOLLOWUP',
                'followup_question': MVPFollowupQuestionSerializer(followup).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
