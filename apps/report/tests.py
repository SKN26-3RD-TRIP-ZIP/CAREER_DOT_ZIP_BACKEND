from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession
from apps.report.models import FinalReport


def failed_summary(session):
  return {
      'evaluation_metadata': {
          'session_id': str(session.id),
          'answer_count': 1,
          'evaluated_answer_count': 0,
          'summary_text': 'AI evaluation failed before completion.',
      },
      'score_summary': {'overall_score': 0, 'metrics': {}},
      'score_detail': {},
      'dynamically_triggered_tags': {},
  }


def success_summary(session):
  return {
      'evaluation_metadata': {
          'session_id': str(session.id),
          'answer_count': 1,
          'evaluated_answer_count': 1,
          'summary_text': 'Evaluation completed.',
      },
      'score_summary': {'overall_score': 82, 'metrics': {}},
      'score_detail': {},
      'dynamically_triggered_tags': {},
  }


class SessionFinalReportAPITests(APITestCase):
  def setUp(self):
    user_model = get_user_model()
    self.user = user_model.objects.create_user(
        email='report-owner@example.com',
        password='password123',
        name='Report Owner',
    )
    self.other_user = user_model.objects.create_user(
        email='report-other@example.com',
        password='password123',
        name='Report Other',
    )
    self.client.force_authenticate(self.user)

  def create_session(self, user=None, status_value='completed'):
    return InterviewSession.objects.create(
        user=user or self.user,
        interview_type='technical',
        persona='practical',
        status=status_value,
    )

  def create_answered_session(self):
    session = self.create_session()
    question = InterviewQuestion.objects.create(
        session=session,
        order_index=1,
        question_type='main',
        question_text='Explain transaction handling.',
        source_type='jd',
    )
    InterviewAnswer.objects.create(
        session=session,
        question=question,
        answer_text='I use atomic transactions.',
    )
    return session

  def report_url(self, session):
    return reverse('session-final-report', kwargs={'session_id': session.id})

  def test_completed_session_creates_and_returns_report(self):
    session = self.create_session()

    response = self.client.get(self.report_url(session))

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(FinalReport.objects.filter(session=session).count(), 1)
    report = FinalReport.objects.get(session=session)
    self.assertEqual(response.data['report_id'], str(report.id))
    self.assertEqual(response.data['session_id'], str(session.id))
    self.assertEqual(response.data['status'], 'completed')
    self.assertIn('generated_at', response.data)
    self.assertEqual(
        set(response.data['summary'].keys()),
        {
            'evaluation_metadata',
            'score_summary',
            'score_detail',
            'dynamically_triggered_tags',
        },
    )

  def test_existing_report_is_returned_without_duplicate_creation(self):
    session = self.create_session()
    report = FinalReport.objects.create(
        session=session,
        summary={
            'evaluation_metadata': {'session_id': str(session.id)},
            'score_summary': {'overall_score': 77, 'metrics': {}},
            'score_detail': {},
            'dynamically_triggered_tags': {},
        },
    )

    response = self.client.get(self.report_url(session))

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data['report_id'], str(report.id))
    self.assertEqual(FinalReport.objects.filter(session=session).count(), 1)
    self.assertEqual(response.data['summary']['score_summary']['overall_score'], 77)
    self.assertEqual(response.data['overall_score'], 77)

  def test_report_overall_score_supports_fallback_shapes(self):
    session = self.create_session()
    report = FinalReport.objects.create(
        session=session,
        summary={
            'raw_data': {
                'summary': {
                    'score_summary': {'overall_score': 64},
                },
            },
        },
    )

    self.assertEqual(report.overall_score, 64)
    report.summary = {'overall_score': 0}
    self.assertEqual(report.overall_score, 0)

  def test_in_progress_session_returns_not_found(self):
    session = self.create_session(status_value='in_progress')

    response = self.client.get(self.report_url(session))

    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    self.assertFalse(FinalReport.objects.filter(session=session).exists())

  def test_other_users_session_returns_not_found(self):
    session = self.create_session(user=self.other_user)

    response = self.client.get(self.report_url(session))

    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

  def test_authentication_is_required(self):
    session = self.create_session()
    self.client.force_authenticate(user=None)

    response = self.client.get(self.report_url(session))

    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

  @patch('apps.report.views.generate_final_report')
  def test_failed_report_summary_is_not_saved_and_returns_retryable_503(self, mock_generate):
    session = self.create_answered_session()
    mock_generate.return_value = failed_summary(session)

    response = self.client.get(self.report_url(session))

    self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
    self.assertEqual(response.data['code'], 'AI_REPORT_GENERATION_FAILED')
    self.assertTrue(response.data['retryable'])
    self.assertFalse(FinalReport.objects.filter(session=session).exists())

  @patch('apps.report.views.generate_final_report')
  def test_failed_report_can_be_retried_without_reusing_zero_score_row(self, mock_generate):
    session = self.create_answered_session()
    mock_generate.side_effect = [failed_summary(session), success_summary(session)]

    first = self.client.get(self.report_url(session))
    second = self.client.get(self.report_url(session))

    self.assertEqual(first.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
    self.assertEqual(second.status_code, status.HTTP_200_OK)
    self.assertEqual(FinalReport.objects.filter(session=session).count(), 1)
    report = FinalReport.objects.get(session=session)
    self.assertEqual(report.summary['score_summary']['overall_score'], 82)
    self.assertEqual(report.summary['evaluation_metadata']['evaluated_answer_count'], 1)
