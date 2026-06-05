from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.common.choices import (
    INTERVIEW_SESSION_STATUS_CANCELLED,
    INTERVIEW_SESSION_STATUS_COMPLETED,
)
from apps.evaluation.models import Evaluation

from .models import InterviewAnswer, InterviewQuestion, InterviewSession


class InterviewSessionCompleteAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='owner@example.com',
            password='password123',
            name='Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='other@example.com',
            password='password123',
            name='Other',
        )
        self.client.force_authenticate(self.user)

    def create_session(self, **kwargs):
        defaults = {
            'user': self.user,
            'interview_type': 'technical',
            'persona': 'coach',
        }
        defaults.update(kwargs)
        return InterviewSession.objects.create(**defaults)

    def complete_url(self, session):
        return reverse('interview-session-complete', kwargs={'session_id': session.id})

    def test_complete_session(self):
        started_at = timezone.now() - timedelta(minutes=30)
        session = self.create_session(status='in_progress', started_at=started_at)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['session_id'], str(session.id))
        self.assertEqual(response.data['status'], INTERVIEW_SESSION_STATUS_COMPLETED)
        self.assertIsNotNone(response.data['ended_at'])
        session.refresh_from_db()
        self.assertEqual(session.status, INTERVIEW_SESSION_STATUS_COMPLETED)
        self.assertIsNotNone(session.ended_at)

    def test_completed_session_is_returned_without_changing_ended_at(self):
        ended_at = timezone.now() - timedelta(minutes=5)
        session = self.create_session(
            status=INTERVIEW_SESSION_STATUS_COMPLETED,
            ended_at=ended_at,
        )

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.assertEqual(session.ended_at, ended_at)

    def test_cancelled_session_cannot_be_completed(self):
        session = self.create_session(status=INTERVIEW_SESSION_STATUS_CANCELLED)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        session.refresh_from_db()
        self.assertEqual(session.status, INTERVIEW_SESSION_STATUS_CANCELLED)

    def test_other_users_session_returns_not_found(self):
        session = self.create_session(user=self.other_user)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authentication_is_required(self):
        session = self.create_session()
        self.client.force_authenticate(user=None)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class InterviewSessionTurnsAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='turn-owner@example.com',
            password='password123',
            name='Turn Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='turn-other@example.com',
            password='password123',
            name='Turn Other',
        )
        self.client.force_authenticate(self.user)
        self.session = InterviewSession.objects.create(
            user=self.user,
            interview_type='technical',
            persona='practical',
            status='in_progress',
        )

    def turns_url(self, session=None):
        return reverse(
            'interview-session-turns',
            kwargs={'session_id': (session or self.session).id},
        )

    def test_turns_include_answers_evaluations_and_follow_ups(self):
        main_question = InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type='main',
            question_text='Main question',
            source_type='general',
        )
        main_answer = InterviewAnswer.objects.create(
            session=self.session,
            question=main_question,
            answer_text='Main answer',
        )
        Evaluation.objects.create(
            answer=main_answer,
            final_tech_score=88,
            llm_concept_score=85,
            score_detail={'summary': 'Good answer'},
        )
        follow_up = InterviewQuestion.objects.create(
            session=self.session,
            order_index=2,
            question_type='follow_up',
            question_text='Follow-up question',
            source_type='general',
            parent_question=main_question,
            source_answer=main_answer,
        )
        InterviewAnswer.objects.create(
            session=self.session,
            question=follow_up,
            answer_text='Follow-up answer',
        )

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 1)
        turn = response.data['turns'][0]
        self.assertEqual(turn['turn_index'], 1)
        self.assertEqual(turn['answer']['answer_text'], 'Main answer')
        self.assertEqual(turn['evaluation']['final_tech_score'], 88)
        self.assertEqual(len(turn['follow_up_questions']), 1)
        self.assertEqual(
            turn['follow_up_questions'][0]['answer']['answer_text'],
            'Follow-up answer',
        )
        self.assertIsNone(turn['follow_up_questions'][0]['evaluation'])

    def test_turn_without_answer_returns_null_values(self):
        InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type='main',
            question_text='Unanswered question',
            source_type='general',
        )

        response = self.client.get(self.turns_url())

        turn = response.data['turns'][0]
        self.assertIsNone(turn['answer'])
        self.assertIsNone(turn['evaluation'])
        self.assertEqual(turn['follow_up_questions'], [])

    def test_other_users_session_returns_not_found(self):
        other_session = InterviewSession.objects.create(
            user=self.other_user,
            interview_type='technical',
            persona='coach',
        )

        response = self.client.get(self.turns_url(other_session))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authentication_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
