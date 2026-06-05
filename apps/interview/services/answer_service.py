from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession


class AnswerService:
    @staticmethod
    def create_answer(*, user, session_id, question_id, answer_text):
        session = AnswerService._get_session(session_id, user)
        question = AnswerService._get_question(question_id)
        if question.session_id != session.id:
            raise ValidationError({'question_id': 'Question does not belong to this session.'})

        normalized_text = answer_text.strip()
        if not normalized_text:
            raise ValidationError({'answer_text': 'Answer text must not be blank.'})
        if InterviewAnswer.objects.filter(question=question).exists():
            raise ValidationError({'question_id': 'An answer already exists for this question.'})

        try:
            with transaction.atomic():
                return InterviewAnswer.objects.create(
                    session=session,
                    question=question,
                    answer_text=normalized_text,
                    answer_source='text',
                )
        except IntegrityError:
            raise ValidationError({'question_id': 'An answer already exists for this question.'})

    @staticmethod
    def get_owned_answer(*, answer_id, user):
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
        try:
            session = InterviewSession.objects.get(id=session_id)
        except InterviewSession.DoesNotExist:
            raise NotFound('Session not found.')
        if session.user_id != user.id:
            raise PermissionDenied('You do not have permission to access this session.')
        return session

    @staticmethod
    def _get_question(question_id):
        try:
            return InterviewQuestion.objects.select_related('session').get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            raise NotFound('Question not found.')
