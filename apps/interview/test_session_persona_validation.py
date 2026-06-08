from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.input.models import JobDescription
from apps.interview.models import InterviewSession


class InterviewSessionPersonaValidationAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='persona-owner@example.com',
            password='password123',
            name='Persona Owner',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Python Django REST API backend development',
        )
        self.client.force_authenticate(self.user)

    def sessions_url(self):
        return reverse('interview-session-list-create')

    def create_payload(self, **overrides):
        payload = {
            'jd_id': str(self.jd.id),
            'interview_type': 'technical',
            'persona': 'practical',
            'total_question_count': 3,
        }
        payload.update(overrides)
        return payload

    def create_session(self, **overrides):
        return self.client.post(
            self.sessions_url(),
            self.create_payload(**overrides),
            format='json',
        )

    def test_session_creation_accepts_official_persona_type(self):
        response = self.create_session(persona='friendly')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['persona'], 'friendly')

        session = InterviewSession.objects.get(id=response.data['session_id'])
        self.assertEqual(session.persona, 'friendly')

    def test_session_creation_normalizes_persona_aliases(self):
        coach_response = self.create_session(persona='coach')
        strict_response = self.create_session(persona='strict')

        self.assertEqual(coach_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(strict_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(coach_response.data['persona'], 'friendly')
        self.assertEqual(strict_response.data['persona'], 'verify')

    def test_session_creation_falls_back_to_practical_when_persona_is_unknown(self):
        response = self.create_session(persona='unknown-persona')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['persona'], 'practical')

        session = InterviewSession.objects.get(id=response.data['session_id'])
        self.assertEqual(session.persona, 'practical')

    def test_session_creation_defaults_to_practical_when_persona_is_missing(self):
        payload = self.create_payload()
        payload.pop('persona')

        response = self.client.post(self.sessions_url(), payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['persona'], 'practical')
