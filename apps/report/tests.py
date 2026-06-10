from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewSession
from apps.report.models import FinalReport


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
