from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.input.models import JobDescription
from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession


class InterviewTurnsFrontendResponseAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='turns-owner@example.com',
            password='password123',
            name='Turns Owner',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Python Django REST API backend development',
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            jd=self.jd,
            interview_type='technical',
            persona='friendly',
            total_question_count=3,
            current_question_index=1,
        )
        self.client.force_authenticate(self.user)

    def turns_url(self):
        return reverse(
            'interview-session-turns',
            kwargs={'session_id': self.session.id},
        )

    def create_main_question(self, order_index, question_text):
        return InterviewQuestion.objects.create(
            session=self.session,
            order_index=order_index,
            question_type='main',
            question_text=question_text,
            source_type='resume',
            source_reference='resume:test',
        )

    def test_turns_response_includes_persona_detail_and_progress(self):
        question_1 = self.create_main_question(
            1,
            '프로젝트에서 본인이 맡은 역할을 설명해주세요.',
        )
        question_2 = self.create_main_question(
            2,
            'Django REST API를 선택한 이유를 설명해주세요.',
        )
        self.create_main_question(
            3,
            '협업 과정에서 겪은 문제를 설명해주세요.',
        )

        answer = InterviewAnswer.objects.create(
            session=self.session,
            question=question_1,
            answer_text='제가 API 설계와 구현을 담당했습니다.',
            answer_source='text',
        )

        InterviewQuestion.objects.create(
            session=self.session,
            order_index=4,
            question_type='follow_up',
            question_text='API 설계에서 본인이 결정한 기준은 무엇인가요?',
            source_type='answer',
            source_reference='followup:test',
            parent_question=question_1,
            source_answer=answer,
        )

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['persona'], 'friendly')
        self.assertEqual(response.data['persona_detail']['persona_type'], 'coach')
        self.assertEqual(response.data['persona_detail']['label'], '친절한 코치형')

        progress = response.data['progress']
        self.assertEqual(progress['main_question_count'], 3)
        self.assertEqual(progress['answered_count'], 1)
        self.assertEqual(progress['follow_up_question_count'], 1)
        self.assertEqual(progress['total_question_count'], 3)
        self.assertEqual(progress['current_question_index'], 1)
        self.assertEqual(progress['completion_rate'], 0.33)

        self.assertEqual(response.data['total'], 3)
        self.assertEqual(len(response.data['turns']), 3)
        self.assertEqual(response.data['turns'][0]['question']['question_id'], str(question_1.id))
        self.assertEqual(response.data['turns'][1]['question']['question_id'], str(question_2.id))

    def test_turns_response_handles_empty_questions(self):
        InterviewQuestion.objects.filter(session=self.session).delete()

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 0)
        self.assertEqual(response.data['turns'], [])
        self.assertEqual(response.data['progress']['main_question_count'], 0)
        self.assertEqual(response.data['progress']['answered_count'], 0)
        self.assertEqual(response.data['progress']['follow_up_question_count'], 0)
        self.assertEqual(response.data['progress']['total_question_count'], 3)
        self.assertEqual(response.data['progress']['completion_rate'], 0.0)
