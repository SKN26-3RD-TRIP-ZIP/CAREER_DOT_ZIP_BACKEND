from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.input.models import JobDescription
from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession


class InterviewTurnsNextActionAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='turns-next-action-owner@example.com',
            password='password123',
            name='Turns Next Action Owner',
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
            persona='practical',
            total_question_count=2,
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

    def test_turns_response_next_action_is_answer_current_question(self):
        question_1 = self.create_main_question(
            1,
            '프로젝트에서 본인이 맡은 역할을 설명해주세요.',
        )
        self.create_main_question(
            2,
            'Django REST API를 선택한 이유를 설명해주세요.',
        )

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['current_turn']['turn_index'], 1)
        self.assertEqual(response.data['current_turn']['question_id'], str(question_1.id))
        self.assertIsNone(response.data['current_turn']['answer_id'])
        self.assertEqual(response.data['next_action']['type'], 'ANSWER_CURRENT_QUESTION')
        self.assertEqual(response.data['next_action']['question_id'], str(question_1.id))
        self.assertIsNone(response.data['next_action']['answer_id'])

    def test_turns_response_next_action_is_generate_follow_up_after_answer(self):
        question_1 = self.create_main_question(
            1,
            '프로젝트에서 본인이 맡은 역할을 설명해주세요.',
        )
        self.create_main_question(
            2,
            'Django REST API를 선택한 이유를 설명해주세요.',
        )

        answer = InterviewAnswer.objects.create(
            session=self.session,
            question=question_1,
            answer_text='제가 API 설계와 구현을 담당했습니다.',
            answer_source='text',
        )

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['current_turn']['turn_index'], 1)
        self.assertEqual(response.data['current_turn']['question_id'], str(question_1.id))
        self.assertEqual(response.data['current_turn']['answer_id'], str(answer.id))
        self.assertEqual(response.data['next_action']['type'], 'GENERATE_FOLLOW_UP')
        self.assertEqual(response.data['next_action']['question_id'], str(question_1.id))
        self.assertEqual(response.data['next_action']['answer_id'], str(answer.id))

    def test_turns_response_next_action_moves_to_next_unanswered_after_follow_up_exists(self):
        question_1 = self.create_main_question(
            1,
            '프로젝트에서 본인이 맡은 역할을 설명해주세요.',
        )
        question_2 = self.create_main_question(
            2,
            'Django REST API를 선택한 이유를 설명해주세요.',
        )

        answer = InterviewAnswer.objects.create(
            session=self.session,
            question=question_1,
            answer_text='제가 API 설계와 구현을 담당했습니다.',
            answer_source='text',
        )
        InterviewQuestion.objects.create(
            session=self.session,
            order_index=3,
            question_type='follow_up',
            question_text='API 설계에서 본인이 결정한 기준은 무엇인가요?',
            source_type='answer',
            source_reference='followup:test',
            parent_question=question_1,
            source_answer=answer,
        )

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['current_turn']['turn_index'], 2)
        self.assertEqual(response.data['current_turn']['question_id'], str(question_2.id))
        self.assertIsNone(response.data['current_turn']['answer_id'])
        self.assertEqual(response.data['next_action']['type'], 'ANSWER_CURRENT_QUESTION')
        self.assertEqual(response.data['next_action']['question_id'], str(question_2.id))

    def test_turns_response_next_action_is_complete_interview_when_all_main_questions_done(self):
        question_1 = self.create_main_question(
            1,
            '프로젝트에서 본인이 맡은 역할을 설명해주세요.',
        )
        question_2 = self.create_main_question(
            2,
            'Django REST API를 선택한 이유를 설명해주세요.',
        )

        answer_1 = InterviewAnswer.objects.create(
            session=self.session,
            question=question_1,
            answer_text='제가 API 설계와 구현을 담당했습니다.',
            answer_source='text',
        )
        answer_2 = InterviewAnswer.objects.create(
            session=self.session,
            question=question_2,
            answer_text='Django는 빠른 API 개발과 ORM 연동에 적합해서 선택했습니다.',
            answer_source='text',
        )

        InterviewQuestion.objects.create(
            session=self.session,
            order_index=3,
            question_type='follow_up',
            question_text='API 설계에서 본인이 결정한 기준은 무엇인가요?',
            source_type='answer',
            source_reference='followup:test1',
            parent_question=question_1,
            source_answer=answer_1,
        )
        InterviewQuestion.objects.create(
            session=self.session,
            order_index=4,
            question_type='follow_up',
            question_text='Django 외 다른 대안과 비교했을 때 기준은 무엇이었나요?',
            source_type='answer',
            source_reference='followup:test2',
            parent_question=question_2,
            source_answer=answer_2,
        )

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['current_turn'])
        self.assertEqual(response.data['next_action']['type'], 'COMPLETE_INTERVIEW')
        self.assertIsNone(response.data['next_action']['question_id'])
        self.assertIsNone(response.data['next_action']['answer_id'])
