"""Active nested REST interview API.

Mounted under /api/v1/interviews/. This surface provides rich session-oriented
responses such as turns, source tags, evaluation data, and progress. The flat
MVP API in mvp_views.py is also active; neither surface should be removed or
merged until consumers agree on a canonical contract.
"""

import hashlib

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.choices import (
    INTERVIEW_SESSION_STATUS_CANCELLED,
    INTERVIEW_SESSION_STATUS_COMPLETED,
)

from .models import InterviewSession
from .serializers import (
    InterviewSessionCompleteSerializer,
    InterviewSessionCreateSerializer,
    InterviewSessionListSerializer,
    InterviewSessionDetailSerializer,
    InterviewSessionStatusSerializer,
)
from .models import GuardrailEvent, InterviewQuestion, QuestionPack, QuestionSourceTag
from .serializers import InterviewQuestionSerializer, QuestionPackCreateSerializer, QuestionPackSerializer
from .services.question_generator import generate_interview_questions
from .services.follow_up_generator import FollowupGenerator
from .services.ai_chain_openai_engine import AIChainOpenAIError
from .services.guardrails import scan_user_input
from .serializers import FollowUpQuestionSerializer
from django.db import models
from django.db.models import Prefetch
from apps.analysis.models import AnalysisSession, JdAnalysis
from apps.accounts.services.points import InsufficientPointsError, apply_point_policy, refund_points
from .models import InterviewAnswer
from .serializers import (
    InterviewAnswerCreateSerializer,
    InterviewAnswerSerializer,
    InterviewTurnSerializer,
    get_persona_detail,
)

EXPECTED_TECHNICAL_KEYWORDS_LABEL = 'expected_technical_keywords'


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
                'persona_type': session.persona,
                'interview_mode': session.interview_mode,
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


def _build_question_pack_questions(interview_type, question_count, mix):
    templates = {
        'technical': [
            'Explain a recent technical decision and the trade-offs you considered.',
            'Describe how you diagnosed and fixed a production-like issue.',
            'How would you design a scalable API for this role?',
            'Tell me about a performance bottleneck you improved.',
            'Which testing strategy would you use for a risky change?',
        ],
        'personality': [
            'Describe a conflict you resolved with a teammate.',
            'Tell me about feedback that changed how you work.',
            'How do you prioritize when deadlines conflict?',
            'Describe a time you owned a mistake and recovered.',
            'What motivates you in this role?',
        ],
        'comprehensive': [
            'Connect your project experience to this job requirement.',
            'Describe a problem, your action, and the measurable result.',
            'What would you learn first after joining this team?',
            'How do you balance speed, quality, and collaboration?',
            'What weakness are you actively improving?',
        ],
    }
    source = templates.get(interview_type, templates['comprehensive'])
    questions = []
    seen = set()
    index = 0
    while len(questions) < question_count:
        text = source[index % len(source)]
        index += 1
        if text in seen:
            text = f'{text} (variant {index})'
        seen.add(text)
        questions.append(
            {
                'order_index': len(questions) + 1,
                'question_text': text,
                'question_type': 'main',
                'question_category': 'technical' if interview_type == 'technical' else 'personality' if interview_type == 'personality' else 'general',
                'difficulty': 'medium',
                'source_type': 'question_pack',
                'source_reference': mix,
            }
        )
    return questions


class QuestionPackListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        packs = QuestionPack.objects.filter(user=request.user).order_by('-created_at')
        return Response(
            {
                'total': packs.count(),
                'results': QuestionPackSerializer(packs[:50], many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = QuestionPackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        question_count = data['question_count']
        interview_type = data['interview_type']
        mix = data.get('mix') or {}
        mix_digest = hashlib.sha256(str(sorted(mix.items())).encode('utf-8')).hexdigest()[:16]
        idempotency_key = f"QUESTION_PACK.CUSTOM:{request.user.id}:{interview_type}:{question_count}:{mix_digest}"

        try:
            charge = apply_point_policy(
                user=request.user,
                reason_code='QUESTION_PACK.CUSTOM',
                reference_id=idempotency_key,
                idempotency_key=idempotency_key,
                description='custom question pack',
            )
        except InsufficientPointsError:
            return Response({'detail': 'Point balance is insufficient.', 'code': 'POINTS_INSUFFICIENT'}, status=402)
        except ValueError as exc:
            return Response({'detail': str(exc), 'code': 'POINT_POLICY_BLOCKED'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            questions = _build_question_pack_questions(interview_type, question_count, mix)
            pack = QuestionPack.objects.create(
                user=request.user,
                title=data.get('title') or f'{interview_type} question pack',
                interview_type=interview_type,
                mix=mix,
                questions=questions,
                prompt_version_snapshot={},
                generation_model='rule-based-mvp',
                is_fallback=False,
            )
        except Exception:
            if charge.created:
                refund_points(
                    user=request.user,
                    amount=abs(charge.history.amount),
                    reason_code='QUESTION_PACK.CUSTOM.REFUND',
                    reference_id=charge.history.reference_id,
                    idempotency_key=f'{charge.history.idempotency_key}:REFUND',
                    description='question pack generation failed',
                )
            raise
        return Response(QuestionPackSerializer(pack).data, status=status.HTTP_201_CREATED)


class QuestionPackDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, question_pack_id):
        pack = get_object_or_404(QuestionPack, id=question_pack_id, user=request.user)
        return Response(QuestionPackSerializer(pack).data, status=status.HTTP_200_OK)


class QuestionPackApplyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, question_pack_id):
        pack = get_object_or_404(QuestionPack, id=question_pack_id, user=request.user)
        session_id = request.data.get('session_id')
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        if session.questions.exists():
            return Response({'detail': 'Session already has questions.', 'code': 'SESSION_QUESTIONS_EXIST'}, status=status.HTTP_409_CONFLICT)

        created = []
        for item in pack.questions:
            created.append(
                InterviewQuestion.objects.create(
                    session=session,
                    order_index=item.get('order_index') or len(created) + 1,
                    question_type=item.get('question_type') or 'main',
                    question_category=item.get('question_category') or 'general',
                    question_text=item.get('question_text') or '',
                    difficulty=item.get('difficulty') or 'medium',
                    source_type='prepared_question',
                    source_reference=str(pack.id),
                )
            )
        session.total_question_count = len(created)
        session.save(update_fields=('total_question_count', 'updated_at'))
        return Response(
            {
                'question_pack_id': str(pack.id),
                'session_id': str(session.id),
                'applied_count': len(created),
                'questions': InterviewQuestionSerializer(created, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


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


class InterviewSessionCompleteView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, session_id):
        session = get_object_or_404(
            InterviewSession,
            id=session_id,
            user=request.user,
        )

        if session.status == INTERVIEW_SESSION_STATUS_CANCELLED:
            return Response(
                {'detail': 'Cancelled session cannot be completed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if session.status != INTERVIEW_SESSION_STATUS_COMPLETED:
            session.status = INTERVIEW_SESSION_STATUS_COMPLETED
            if session.ended_at is None:
                session.ended_at = timezone.now()
            session.save(update_fields=('status', 'ended_at', 'updated_at'))
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

        serializer = InterviewSessionCompleteSerializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InterviewSessionTurnsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(
            InterviewSession,
            id=session_id,
            user=request.user,
        )
        follow_up_queryset = InterviewQuestion.objects.select_related(
            'answer__evaluation',
        ).order_by('order_index')
        main_questions = (
            InterviewQuestion.objects.filter(
                session=session,
                question_type='main',
            )
            .select_related('answer__evaluation')
            .prefetch_related(
                Prefetch(
                    'answer__follow_up_questions',
                    queryset=follow_up_queryset,
                    to_attr='prefetched_follow_up_questions',
                )
            )
            .order_by('order_index')
        )
        turns = [
            {'turn_index': index, 'question': question}
            for index, question in enumerate(main_questions, start=1)
        ]

        answered_count = 0
        follow_up_question_count = 0
        first_unanswered_turn = None
        pending_follow_up_turn = None
        pending_follow_up_answer = None

        for turn in turns:
            question = turn['question']
            try:
                answer = question.answer
            except InterviewAnswer.DoesNotExist:
                answer = None

            if answer:
                answered_count += 1
                follow_up_questions = getattr(answer, 'prefetched_follow_up_questions', [])
                follow_up_question_count += len(follow_up_questions)

                if not follow_up_questions and pending_follow_up_answer is None:
                    pending_follow_up_turn = turn
                    pending_follow_up_answer = answer
            elif first_unanswered_turn is None:
                first_unanswered_turn = turn

        main_question_count = len(turns)
        total_question_count = session.total_question_count or main_question_count
        completion_rate = (
            round(answered_count / total_question_count, 2)
            if total_question_count
            else 0
        )

        current_turn = None
        next_action = {
            'type': 'COMPLETE_INTERVIEW',
            'question_id': None,
            'answer_id': None,
        }

        if pending_follow_up_answer is not None and pending_follow_up_turn is not None:
            pending_question = pending_follow_up_turn['question']
            current_turn = {
                'turn_index': pending_follow_up_turn['turn_index'],
                'question_id': str(pending_question.id),
                'answer_id': str(pending_follow_up_answer.id),
            }
            next_action = {
                'type': 'GENERATE_FOLLOW_UP',
                'question_id': str(pending_question.id),
                'answer_id': str(pending_follow_up_answer.id),
            }
        elif first_unanswered_turn is not None:
            unanswered_question = first_unanswered_turn['question']
            current_turn = {
                'turn_index': first_unanswered_turn['turn_index'],
                'question_id': str(unanswered_question.id),
                'answer_id': None,
            }
            next_action = {
                'type': 'ANSWER_CURRENT_QUESTION',
                'question_id': str(unanswered_question.id),
                'answer_id': None,
            }

        return Response(
            {
                'session_id': str(session.id),
                'interview_type': session.interview_type,
                'persona': session.persona,
                'persona_detail': get_persona_detail(session.persona),
                'status': session.status,
                'total': len(turns),
                'progress': {
                    'main_question_count': main_question_count,
                    'answered_count': answered_count,
                    'follow_up_question_count': follow_up_question_count,
                    'total_question_count': total_question_count,
                    'current_question_index': session.current_question_index,
                    'completion_rate': completion_rate,
                },
                'current_turn': current_turn,
                'next_action': next_action,
                'turns': InterviewTurnSerializer(turns, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


def _save_question_source_tags(question, source_tags):
    normalized_tags = []
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

        normalized_tags.append(
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

    if normalized_tags:
        QuestionSourceTag.objects.bulk_create(normalized_tags)


def _resolve_requested_jd_analysis(request, session):
    jd_analysis_id = request.data.get('jd_analysis_id')
    analysis_session_id = request.data.get('analysis_session_id')
    jd_analysis = None

    if jd_analysis_id:
        jd_analysis = JdAnalysis.objects.filter(
            id=jd_analysis_id,
            user=request.user,
        ).first()
        if not jd_analysis:
            return None, Response(
                {'jd_analysis_id': 'JD analysis not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if analysis_session_id:
        analysis_session = (
            AnalysisSession.objects.select_related('jd_analysis')
            .filter(id=analysis_session_id, user=request.user)
            .first()
        )
        if not analysis_session:
            return None, Response(
                {'analysis_session_id': 'Analysis session not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not analysis_session.jd_analysis_id:
            return None, Response(
                {'analysis_session_id': 'Analysis session has no completed result.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if jd_analysis and jd_analysis.id != analysis_session.jd_analysis_id:
            return None, Response(
                {'jd_analysis_id': 'JD analysis does not match analysis_session_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        jd_analysis = analysis_session.jd_analysis

    if not jd_analysis:
        return None, None

    if session.jd_id and session.jd_id != jd_analysis.jd_id:
        return None, Response(
            {'jd_analysis_id': 'JD analysis does not match this session.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if session.resume_id and session.resume_id != jd_analysis.resume_id:
        return None, Response(
            {'jd_analysis_id': 'JD analysis does not match this session.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if session.cover_letter_id and session.cover_letter_id != jd_analysis.cover_letter_id:
        return None, Response(
            {'jd_analysis_id': 'JD analysis does not match this session.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return jd_analysis, None


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
        jd_analysis, error_response = _resolve_requested_jd_analysis(request, session)
        if error_response:
            return error_response
        if jd_analysis:
            session._jd_analysis_id = jd_analysis.id

        try:
            from apps.interview.mvp_views import get_prompt_version_id

            prompt_version_id = get_prompt_version_id(session)
        except Exception:
            prompt_version_id = None
        if prompt_version_id:
            snapshot = dict(session.prompt_version_snapshot or {})
            snapshot['question_generation'] = str(prompt_version_id)
            session.prompt_version_snapshot = snapshot
            session.save(update_fields=('prompt_version_snapshot', 'updated_at'))

        try:
            generated = generate_interview_questions(session)
        except AIChainOpenAIError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "error_code": "llm_generation_failed",
                    "chain": exc.chain_name,
                    "retryable": True,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        created = []
        for q in generated:
            iq = InterviewQuestion.objects.create(
                session=session,
                order_index=q.get('order_index'),
                question_type=q.get('question_type'),
                question_category=q.get('question_category', 'general'),
                question_text=q.get('question_text'),
                difficulty=q.get('difficulty'),
                source_type=q.get('source_type'),
                source_reference=q.get('source_reference'),
            )
            _save_question_source_tags(iq, q.get('source_tags'))
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


class InterviewAnswerSaveView(APIView):
    """Save or replace an answer under the nested REST contract."""

    permission_classes = [permissions.IsAuthenticated]

    def get_session(self, session_id):
        try:
            return InterviewSession.objects.get(id=session_id, user=self.request.user)
        except InterviewSession.DoesNotExist:
            return None

    def post(self, request, session_id, question_id):
        session = self.get_session(session_id)
        if not session:
            return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            question = InterviewQuestion.objects.get(id=question_id, session=session)
        except InterviewQuestion.DoesNotExist:
            return Response({'detail': 'Question not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = InterviewAnswerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        previous_answers = (
            InterviewAnswer.objects
            .filter(session=session)
            .exclude(question=question)
            .values_list('answer_text', flat=True)
        )
        guardrail = scan_user_input(data.get('answer_text'), previous_answers=previous_answers)
        guardrail_event = GuardrailEvent.objects.create(
            user=request.user,
            session=session,
            question=question,
            category=guardrail.category,
            action=guardrail.action,
            stage='INTERVIEW',
            direction='USER_TO_AI',
            rule_source='RULE',
            reason_code=guardrail.reason_code,
            masked_excerpt=guardrail.masked_excerpt,
            endpoint='interview_answer_save',
        )

        if guardrail.should_block:
            return Response(
                {
                    'detail': '입력 내용을 저장할 수 없습니다.',
                    'guardrail': guardrail.as_response(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        answer_obj, created = InterviewAnswer.objects.update_or_create(
            question=question,
            defaults={
                'session': session,
                'answer_text': data.get('answer_text'),
                'answer_source': data.get('answer_source', 'text'),
            },
        )
        guardrail_event.answer = answer_obj
        guardrail_event.save(update_fields=['answer'])

        out_serializer = InterviewAnswerSerializer(answer_obj)
        response_data = dict(out_serializer.data)
        response_data['guardrail'] = guardrail.as_response()
        return Response(response_data, status=(status.HTTP_201_CREATED if created else status.HTTP_200_OK))


class InterviewAnswerListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.kwargs.get('session_id')
        return InterviewAnswer.objects.filter(session__id=session_id, session__user=self.request.user).select_related('question').order_by('question__order_index')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        results = []
        for ans in queryset:
            results.append({
                'answer_id': str(ans.id),
                'question_id': str(ans.question.id),
                'order_index': ans.question.order_index,
                'question_text': ans.question.question_text,
                'answer_text': ans.answer_text,
                'answer_source': ans.answer_source,
                'created_at': ans.created_at,
            })

        return Response({'session_id': kwargs.get('session_id'), 'total': queryset.count(), 'results': results}, status=status.HTTP_200_OK)


class FollowUpGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_session(self, session_id):
        try:
            return InterviewSession.objects.get(id=session_id, user=self.request.user)
        except InterviewSession.DoesNotExist:
            return None

    def post(self, request, session_id, answer_id):
        session = self.get_session(session_id)
        if not session:
            return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            answer = InterviewAnswer.objects.get(id=answer_id, session=session)
        except InterviewAnswer.DoesNotExist:
            return Response({'detail': 'Answer not found.'}, status=status.HTTP_404_NOT_FOUND)

        force = request.data.get('force_regenerate', False)
        existing = InterviewQuestion.objects.filter(
            source_answer=answer,
            question_type='follow_up',
        ).order_by('order_index')

        if existing.exists() and not force:
            serializer = FollowUpQuestionSerializer(existing, many=True)
            return Response(
                {
                    'session_id': str(session.id),
                    'answer_id': str(answer.id),
                    'total': existing.count(),
                    'follow_up_questions': serializer.data,
                    'next_action': 'GENERATE_FOLLOWUP',
                },
                status=status.HTTP_200_OK,
            )

        if force:
            existing.delete()

        try:
            followup, created = FollowupGenerator.create_followup(answer)
        except AIChainOpenAIError as exc:
            return Response(
                {
                    'detail': '꼬리질문 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.',
                    'code': 'AI_FOLLOWUP_GENERATION_FAILED',
                    'error_code': 'AI_FOLLOWUP_GENERATION_FAILED',
                    'chain': exc.chain_name,
                    'retryable': True,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if followup is None:
            return Response(
                {
                    'session_id': str(session.id),
                    'answer_id': str(answer.id),
                    'total': 0,
                    'follow_up_questions': [],
                    'next_action': 'NEXT_QUESTION',
                },
                status=status.HTTP_200_OK,
            )

        serializer = FollowUpQuestionSerializer([followup], many=True)
        return Response(
            {
                'session_id': str(session.id),
                'answer_id': str(answer.id),
                'total': 1,
                'follow_up_questions': serializer.data,
                'next_action': 'GENERATE_FOLLOWUP',
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class FollowUpListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FollowUpQuestionSerializer

    def get_queryset(self):
        session_id = self.kwargs.get('session_id')
        return InterviewQuestion.objects.filter(session__id=session_id, session__user=self.request.user, question_type='follow_up').order_by('order_index')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({'session_id': kwargs.get('session_id'), 'total': queryset.count(), 'results': serializer.data}, status=status.HTTP_200_OK)


class InterviewPersonaListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .serializers import InterviewPersonaSerializer
        from .services.ai_chain_persona_prompts import get_persona_options

        personas = get_persona_options()
        serializer = InterviewPersonaSerializer(personas, many=True)
        return Response(
            {
                'total': len(personas),
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
