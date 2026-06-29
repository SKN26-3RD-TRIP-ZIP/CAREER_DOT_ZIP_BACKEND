"""Active flat MVP interview API.

Mounted directly under /api/v1/. This surface provides compact frontend
responses, alias conversion, STT/TTS, and MVP follow-up actions. The nested
REST API in views.py is also active; neither surface should be removed or
merged until consumers agree on a canonical contract.
"""

from django.shortcuts import get_object_or_404
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import parsers
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.prompt.models import AdminPromptTestRun, PersonaConfig, PromptVersion
from apps.accounts.services.points import InsufficientPointsError, apply_point_policy, refund_points
from .models import InterviewAnswer, InterviewQuestion, InterviewSession, QuestionSourceTag
from .mvp_serializers import (
    MVPQuestionGenerateSerializer,
    MVPQuestionSerializer,
    MVPAnswerCreateSerializer,
    MVPSTTResultUpdateSerializer,
    MVPFollowupQuestionSerializer,
    PracticeSessionCreateSerializer,
    MVPSessionCreateSerializer,
    MVPSessionStatusSerializer,
    STATUS_INPUT_MAP,
    serialize_mvp_session,
)
from .services.question_generator import generate_interview_questions
from .services.answer_service import AnswerService
from .services.follow_up_generator import FollowupGenerator
from .services.whisper_stt_service import transcribe_uploaded_audio
from .services.tts_service import synthesize_interview_question
from .services.ai_chain_openai_engine import AIChainOpenAIError
from .services.practice_session_service import (
    PracticeSessionCreationError,
    create_practice_session,
)

EXPECTED_TECHNICAL_KEYWORDS_LABEL = 'expected_technical_keywords'


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


class MVPPracticeSessionCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, source_session_id):
        source_session = get_object_or_404(
            InterviewSession,
            id=source_session_id,
            user=request.user,
        )
        serializer = PracticeSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = f'PRACTICE.WEAKNESS_FOCUS:{request.user.id}:{source_session.id}'

        try:
            charge = apply_point_policy(
                user=request.user,
                reason_code='PRACTICE.WEAKNESS_FOCUS',
                reference_id=str(source_session.id),
                idempotency_key=idempotency_key,
                description='weakness focus practice',
            )
        except InsufficientPointsError:
            return Response({'detail': 'Point balance is insufficient.', 'code': 'POINTS_INSUFFICIENT'}, status=402)
        except ValueError as exc:
            return Response({'detail': str(exc), 'code': 'POINT_POLICY_BLOCKED'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = create_practice_session(
                source_session=source_session,
                question_count=serializer.validated_data["question_count"],
                persona=serializer.validated_data.get("persona_type"),
                interview_mode=serializer.validated_data.get("interview_mode"),
            )
        except PracticeSessionCreationError as exc:
            if charge.created:
                refund_points(
                    user=request.user,
                    amount=abs(charge.history.amount),
                    reason_code='PRACTICE.WEAKNESS_FOCUS.REFUND',
                    reference_id=str(source_session.id),
                    idempotency_key=f'{idempotency_key}:REFUND',
                    description='weakness focus practice failed',
                )
            return Response(
                {
                    "detail": exc.detail,
                    "code": exc.code,
                    "error_code": exc.code,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        practice_session = result["session"]
        questions = result["questions"]
        return Response(
            {
                "source_session_id": str(source_session.id),
                "session_id": str(practice_session.id),
                "status": "ready",
                "persona_type": serialize_mvp_session(practice_session)["persona_type"],
                "interview_mode": practice_session.interview_mode,
                "weakness_tags": result["weakness_tags"],
                "generated_count": len(questions),
                "questions": MVPQuestionSerializer(questions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MVPSessionStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, session_id):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        serializer = MVPSessionStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data['status']
        was_completed = session.status == 'completed'
        session.status = STATUS_INPUT_MAP[requested_status]
        if requested_status == 'in_progress' and session.started_at is None:
            session.started_at = timezone.now()
        if requested_status in {'completed', 'canceled', 'failed'} and session.ended_at is None:
            session.ended_at = timezone.now()
        session.save(update_fields=('status', 'started_at', 'ended_at', 'updated_at'))
        if requested_status == 'completed' and not was_completed:
            try:
                apply_point_policy(
                    user=request.user,
                    reason_code='INTERVIEW.COMPLETED',
                    reference_id=str(session.id),
                    idempotency_key=f'INTERVIEW.COMPLETED:{session.id}',
                    description='interview completed',
                )
            except ValueError:
                pass
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
    seen_labels = set(
        question.source_tags.values_list('source_label', flat=True)
    )

    for tag in source_tags or []:
        if not isinstance(tag, dict):
            continue

        source_label = tag.get('source_label') or ''
        if source_label == EXPECTED_TECHNICAL_KEYWORDS_LABEL:
            if question.question_category != 'technical':
                continue
            if source_label in seen_labels:
                continue
            source_text_excerpt = (tag.get('source_text_excerpt') or '').strip()
            if not source_text_excerpt:
                continue
        else:
            source_text_excerpt = tag.get('source_text_excerpt') or ''

        source_tag_objects.append(
            QuestionSourceTag(
                question=question,
                source_type=tag.get('source_type') or question.source_type or 'general',
                source_label=source_label,
                source_text_excerpt=source_text_excerpt,
                source_reference=tag.get('source_reference') or question.source_reference or '',
            )
        )
        if source_label:
            seen_labels.add(source_label)

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

        jd_analysis = serializer.validated_data.get('jd_analysis')
        if jd_analysis:
            session._jd_analysis_id = jd_analysis.id

        project_ids = serializer.validated_data.get('project_ids') or []
        if project_ids:
            session._project_ids = [str(project_id) for project_id in project_ids]

        prompt_version_id = serializer.validated_data.get('prompt_version_id')
        resolved_prompt_version_id = prompt_version_id or get_prompt_version_id(session)
        if resolved_prompt_version_id:
            snapshot = dict(session.prompt_version_snapshot or {})
            snapshot['question_generation'] = str(resolved_prompt_version_id)
            session.prompt_version_snapshot = snapshot
            session.save(update_fields=('prompt_version_snapshot', 'updated_at'))
        if prompt_version_id:
            AdminPromptTestRun.objects.get_or_create(
                session=session,
                defaults={
                    'admin_user': request.user,
                    'prompt_version': PromptVersion.objects.get(id=prompt_version_id),
                },
            )

        try:
            generated = generate_interview_questions(
                session,
                prompt_version_id=prompt_version_id,
            )
        except AIChainOpenAIError as exc:
            if prompt_version_id:
                session.delete()
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
                question_category=question.get('question_category', 'general'),
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
    """Create one answer; the MVP contract rejects duplicate answers."""

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
        # answer_id만으로 수정하지 않고 session__user 조건을 함께 걸어 답변 소유권을 검증한다.
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
        # 음성 답변도 기존 평가/리포트 흐름을 그대로 타도록 answer_text에 STT 텍스트를 동기화한다.
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
        # 프론트 MediaRecorder가 보낸 multipart webm 파일을 Whisper STT 서비스로 전달한다.
        audio_file = request.FILES.get('audio')
        language = request.data.get('language') or 'ko'
        result = transcribe_uploaded_audio(audio_file, language=language)
        return Response(result, status=status.HTTP_200_OK)


class MVPWhisperDevTranscribeView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        # 인증 없이 테스트할 수 있는 dev endpoint지만, 운영에서는 DEBUG가 아니면 차단한다.
        if not settings.DEBUG:
            return Response(
                {'detail': 'Development STT endpoint is disabled.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        audio_file = request.FILES.get('audio')
        language = request.data.get('language') or 'ko'
        result = transcribe_uploaded_audio(audio_file, language=language)
        return Response(result, status=status.HTTP_200_OK)


class MVPTTSSpeechView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get('session_id')
        # 세션 소유권을 먼저 확인하고, 세션 persona로 면접관 목소리를 선택한다.
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        result = synthesize_interview_question(
            request.data.get('text'),
            persona=session.persona,
        )
        # mp3 bytes는 응답 본문으로, 생성에 사용한 모델/voice/persona는 헤더로 내려준다.
        response = HttpResponse(result['audio_bytes'], content_type=result['content_type'])
        response['X-TTS-Model'] = result['model']
        response['X-TTS-Voice'] = result['voice']
        response['X-TTS-Persona'] = result['persona']
        return response


class MVPFollowupQuestionCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, answer_id):
        # 답변 저장 후 충분성 판단 결과에 따라 현재 질문 뒤에 붙일 꼬리질문을 생성한다.
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
