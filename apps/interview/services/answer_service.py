from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.interview.models import GuardrailEvent, InterviewAnswer, InterviewQuestion, InterviewSession
from apps.interview.services.guardrails import scan_user_input


class AnswerService:
    @staticmethod
    def create_answer(*, user, session_id, question_id, answer_text, speech_duration=None, answer_source='text'):
        # 세션/질문 소유권과 연결 관계를 서비스 계층에서 한 번 더 확인한다.
        session = AnswerService._get_session(session_id, user)
        question = AnswerService._get_question(question_id)
        if question.session_id != session.id:
            raise ValidationError({'question_id': 'Question does not belong to this session.'})

        normalized_text = answer_text.strip()
        if not normalized_text:
            raise ValidationError({'answer_text': 'Answer text must not be blank.'})
        if InterviewAnswer.objects.filter(question=question).exists():
            raise ValidationError({'question_id': 'An answer already exists for this question.'})
        if answer_source not in {'text', 'stt'}:
            raise ValidationError({'answer_source': 'Answer source must be text or stt.'})
        previous_answers = (
            InterviewAnswer.objects
            .filter(session=session)
            .exclude(question=question)
            .values_list('answer_text', flat=True)
        )
        guardrail = scan_user_input(normalized_text, previous_answers=previous_answers)
        guardrail_event = GuardrailEvent.objects.create(
            user=user,
            session=session,
            question=question,
            category=guardrail.category,
            action=guardrail.action,
            stage='INTERVIEW',
            direction='USER_TO_AI',
            rule_source='RULE',
            reason_code=guardrail.reason_code,
            masked_excerpt=guardrail.masked_excerpt,
            endpoint='mvp_answer_create',
        )
        if guardrail.should_block:
            raise ValidationError({'answer_text': 'Input was blocked by guardrail.', 'guardrail': guardrail.as_response()})

        try:
            # 같은 질문에 중복 답변이 생기지 않도록 DB 저장을 트랜잭션으로 묶는다.
            with transaction.atomic():
                answer = InterviewAnswer.objects.create(
                    session=session,
                    question=question,
                    answer_text=normalized_text,
                    answer_source=answer_source,
                    speech_duration=speech_duration,
                )
                guardrail_event.answer = answer
                guardrail_event.save(update_fields=['answer'])
                return answer
        except IntegrityError:
            raise ValidationError({'question_id': 'An answer already exists for this question.'})

    @staticmethod
    def get_owned_answer(*, answer_id, user):
        # 꼬리질문 생성처럼 answer_id만 받는 API에서 공통으로 쓰는 소유권 확인 헬퍼.
        try:
            answer = InterviewAnswer.objects.select_related(
                'session',
                'question',
            ).get(id=answer_id)
        except InterviewAnswer.DoesNotExist:
            raise NotFound('Answer not found.')
        if answer.session.user_id != user.id:
            raise PermissionDenied('You do not have permission to access this answer.')
        return answer

    @staticmethod
    def _get_session(session_id, user):
        # 세션은 반드시 요청 사용자 소유여야 답변을 생성할 수 있다.
        try:
            session = InterviewSession.objects.get(id=session_id)
        except InterviewSession.DoesNotExist:
            raise NotFound('Session not found.')
        if session.user_id != user.id:
            raise PermissionDenied('You do not have permission to access this session.')
        return session

    @staticmethod
    def _get_question(question_id):
        # 질문 존재 여부만 먼저 확인하고, 세션 매칭은 create_answer에서 별도로 검증한다.
        try:
            return InterviewQuestion.objects.select_related('session').get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            raise NotFound('Question not found.')
