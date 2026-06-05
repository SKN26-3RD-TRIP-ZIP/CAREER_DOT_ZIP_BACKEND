from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession
from apps.report.models import FinalReport


class InterviewHistoryAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='mypage-owner@example.com',
            password='password123',
            name='Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='mypage-other@example.com',
            password='password123',
            name='Other',
        )
        self.client.force_authenticate(self.user)
        self.url = reverse('mypage-interview-history')

    def create_session(self, user=None, **kwargs):
        return InterviewSession.objects.create(
            user=user or self.user,
            interview_type='technical',
            persona='practical',
            **kwargs,
        )

    def test_history_returns_counts_and_report(self):
        session = self.create_session(status='completed')
        question = InterviewQuestion.objects.create(
            session=session,
            order_index=1,
            question_type='main',
            question_text='Question',
            source_type='general',
        )
        InterviewAnswer.objects.create(
            session=session,
            question=question,
            answer_text='Answer',
        )
        report = FinalReport.objects.create(
            user=self.user,
            session=session,
            overall_score=88,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 1)
        result = response.data['results'][0]
        self.assertEqual(result['question_count'], 1)
        self.assertEqual(result['answer_count'], 1)
        self.assertTrue(result['has_report'])
        self.assertEqual(result['report_id'], str(report.id))
        self.assertEqual(result['overall_score'], 88)

    def test_history_filters_status_applies_limit_and_excludes_other_user(self):
        self.create_session(status='completed')
        self.create_session(status='completed')
        self.create_session(status='created')
        self.create_session(user=self.other_user, status='completed')

        response = self.client.get(self.url, {'status': 'completed', 'limit': 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 2)
        self.assertEqual(len(response.data['results']), 1)

    def test_history_without_report_returns_null_values(self):
        self.create_session()

        response = self.client.get(self.url)

        result = response.data['results'][0]
        self.assertFalse(result['has_report'])
        self.assertIsNone(result['report_id'])
        self.assertIsNone(result['overall_score'])

    def test_invalid_query_parameters_return_bad_request(self):
        invalid_limit = self.client.get(self.url, {'limit': 0})
        invalid_status = self.client.get(self.url, {'status': 'unknown'})

        self.assertEqual(invalid_limit.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_status.status_code, status.HTTP_400_BAD_REQUEST)

    def test_authentication_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
