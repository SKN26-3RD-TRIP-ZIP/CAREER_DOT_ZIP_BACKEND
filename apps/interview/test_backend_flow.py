from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.evaluation.models import Evaluation
from apps.input.models import JobDescription, ResumeMaster
from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession
from apps.report.models import FinalReport


# 리포트 비동기 생성을 테스트에서는 인라인(EAGER)으로 실행해 결정성을 확보한다.
@override_settings(REPORT_GENERATION_EAGER=True)
class BackendMVPFlowIntegrationTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='flow-owner@example.com',
            password='password123',
            name='Flow Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='flow-other@example.com',
            password='password123',
            name='Flow Other',
        )
        self.client.force_authenticate(self.user)

    def create_jd(self, user=None):
        return JobDescription.objects.create(
            user=user or self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Python Django REST API development',
            input_method='TEXT',
            keywords='Python,Django,API',
        )

    def create_resume(self, user=None):
        return ResumeMaster.objects.create(
            user=user or self.user,
            name='Flow Owner',
            email='flow-owner@example.com',
            original_text='Backend developer with Python and Django experience.',
            extracted_keywords='Python,Django,API',
        )

    def create_session_with_answer_and_evaluation(self, user=None, status_value='in_progress'):
        owner = user or self.user
        session = InterviewSession.objects.create(
            user=owner,
            jd=self.create_jd(owner),
            resume=self.create_resume(owner),
            interview_type='technical',
            persona='practical',
            status=status_value,
            interview_mode='text',
        )
        question = InterviewQuestion.objects.create(
            session=session,
            order_index=1,
            question_type='main',
            question_text='RESTful API design principles?',
            source_type='general',
            source_reference='FLOW_TEST',
        )
        answer = InterviewAnswer.objects.create(
            session=session,
            question=question,
            answer_text='I designed Django REST APIs and improved response time by 30%.',
            answer_source='text',
        )
        Evaluation.objects.create(
            answer=answer,
            bei_score={'score': 80},
            cbi_score={'score': 86},
            llm_concept_score=85,
            answer_score=88,
            score_detail={
                'summary': 'Technically solid answer.',
                'improvement': 'Add more business impact details.',
            },
        )
        return session

    def complete_url(self, session):
        return reverse('interview-session-complete', kwargs={'session_id': session.id})

    def report_url(self, session):
        return reverse('session-final-report', kwargs={'session_id': session.id})

    def test_backend_flow_from_session_completion_to_final_report(self):
        session = self.create_session_with_answer_and_evaluation(status_value='in_progress')

        complete_response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(complete_response.data['status'], 'completed')
        session.refresh_from_db()
        self.assertEqual(session.status, 'completed')

        report_response = self.client.get(self.report_url(session))

        self.assertEqual(report_response.status_code, status.HTTP_200_OK)
        self.assertIn('report_id', report_response.data)
        self.assertEqual(report_response.data['session_id'], str(session.id))
        self.assertEqual(report_response.data['status'], 'completed')
        self.assertTrue(FinalReport.objects.filter(session=session).exists())

        summary = report_response.data['summary']
        self.assertIn('evaluation_metadata', summary)
        self.assertIn('score_summary', summary)
        self.assertIn('score_detail', summary)
        self.assertIn('dynamically_triggered_tags', summary)
        self.assertEqual(summary['score_summary']['overall_score'], 88)

    def test_uncompleted_session_report_returns_not_found(self):
        session = self.create_session_with_answer_and_evaluation(status_value='in_progress')

        response = self.client.get(self.report_url(session))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(FinalReport.objects.filter(session=session).exists())

    def test_other_users_session_report_returns_not_found(self):
        session = self.create_session_with_answer_and_evaluation(
            user=self.other_user,
            status_value='completed',
        )

        response = self.client.get(self.report_url(session))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
