from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.input.models import JobDescription
from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession


class InterviewMVPE2EFlowAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='interview-e2e-owner@example.com',
            password='password123',
            name='Interview E2E Owner',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text=(
                'Django REST Framework 기반 API 개발, OpenAI API 연동, '
                '면접 질문 생성 및 답변 평가 기능 구현 경험을 요구합니다.'
            ),
        )
        self.client.force_authenticate(self.user)

    def test_interview_mvp_e2e_api_flow(self):
        persona_response = self.client.get(reverse('interview-persona-list'))

        self.assertEqual(persona_response.status_code, status.HTTP_200_OK)
        self.assertIn('results', persona_response.data)
        self.assertTrue(
            any(
                persona['persona_type'] == 'practical'
                for persona in persona_response.data['results']
            )
        )

        session_response = self.client.post(
            reverse('interview-session-list-create'),
            {
                'jd_id': str(self.jd.id),
                'interview_type': 'technical',
                'persona': 'friendly',
                'total_question_count': 3,
            },
            format='json',
        )

        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        session_id = session_response.data['session_id']
        self.assertEqual(session_response.data['persona'], 'friendly')

        status_response = self.client.patch(
            reverse(
                'interview-session-status-update',
                kwargs={'session_id': session_id},
            ),
            {'status': 'in_progress'},
            format='json',
        )

        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data['status'], 'in_progress')

        question_generate_response = self.client.post(
            reverse(
                'interview-question-generate',
                kwargs={'session_id': session_id},
            ),
            {},
            format='json',
        )

        self.assertIn(
            question_generate_response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
        )
        self.assertGreaterEqual(question_generate_response.data['total'], 1)
        questions = question_generate_response.data['questions']
        first_question = questions[0]

        self.assertIn('question_id', first_question)
        self.assertEqual(first_question['question_type'], 'main')

        question_list_response = self.client.get(
            reverse(
                'interview-question-list',
                kwargs={'session_id': session_id},
            )
        )

        self.assertEqual(question_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            question_list_response.data['total'],
            question_generate_response.data['total'],
        )

        initial_turns_response = self.client.get(
            reverse(
                'interview-session-turns',
                kwargs={'session_id': session_id},
            )
        )

        self.assertEqual(initial_turns_response.status_code, status.HTTP_200_OK)
        self.assertIn('progress', initial_turns_response.data)
        self.assertIn('current_turn', initial_turns_response.data)
        self.assertIn('next_action', initial_turns_response.data)
        self.assertEqual(
            initial_turns_response.data['next_action']['type'],
            'ANSWER_CURRENT_QUESTION',
        )

        answer_response = self.client.post(
            reverse(
                'interview-answer-save',
                kwargs={
                    'session_id': session_id,
                    'question_id': first_question['question_id'],
                },
            ),
            {
                'answer_text': '제가 직접 구현했습니다.',
                'answer_source': 'text',
            },
            format='json',
        )

        self.assertIn(
            answer_response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
        )
        answer_id = answer_response.data['answer_id']

        self.assertTrue(InterviewAnswer.objects.filter(id=answer_id).exists())

        followup_generate_response = self.client.post(
            reverse(
                'follow-up-generate',
                kwargs={
                    'session_id': session_id,
                    'answer_id': answer_id,
                },
            ),
            {},
            format='json',
        )

        self.assertIn(
            followup_generate_response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
        )
        self.assertIn('follow_up_questions', followup_generate_response.data)

        followup_list_response = self.client.get(
            reverse(
                'follow-up-list',
                kwargs={'session_id': session_id},
            )
        )

        self.assertEqual(followup_list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(followup_list_response.data['total'], 1)

        updated_turns_response = self.client.get(
            reverse(
                'interview-session-turns',
                kwargs={'session_id': session_id},
            )
        )

        self.assertEqual(updated_turns_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(
            updated_turns_response.data['progress']['answered_count'],
            1,
        )
        self.assertGreaterEqual(
            updated_turns_response.data['progress']['follow_up_question_count'],
            1,
        )
        self.assertIsNotNone(updated_turns_response.data['turns'][0]['answer'])
        self.assertGreaterEqual(
            len(updated_turns_response.data['turns'][0]['follow_up_questions']),
            1,
        )

        complete_response = self.client.patch(
            reverse(
                'interview-session-complete',
                kwargs={'session_id': session_id},
            ),
            {},
            format='json',
        )

        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(complete_response.data['status'], 'completed')

        session = InterviewSession.objects.get(id=session_id)
        self.assertEqual(session.status, 'completed')
        self.assertGreaterEqual(
            InterviewQuestion.objects.filter(session=session, question_type='main').count(),
            1,
        )
        self.assertGreaterEqual(
            InterviewQuestion.objects.filter(session=session, question_type='follow_up').count(),
            1,
        )
