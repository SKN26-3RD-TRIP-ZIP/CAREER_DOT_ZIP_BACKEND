from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession


class InterviewAudioPlaybackAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='audio-owner@example.com', password='password123', name='Audio Owner'
        )
        self.other_user = user_model.objects.create_user(
            email='audio-other@example.com', password='password123', name='Audio Other'
        )
        self.session = InterviewSession.objects.create(
            user=self.user, interview_type='technical', persona='coach', interview_mode='voice'
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session, order_index=1, question_text='음성 질문'
        )
        self.answer = InterviewAnswer.objects.create(
            session=self.session,
            question=self.question,
            answer_text='충분한 길이의 음성 면접 답변입니다.',
            audio_key=f'interview-audio/{self.user.id}/{self.session.id}/answer.webm',
        )
        self.url = reverse('mvp-answer-audio', kwargs={'answer_id': self.answer.id})

    @patch(
        'apps.interview.mvp_views.create_interview_audio_presigned_url',
        return_value='https://signed.example/audio',
    )
    def test_owner_receives_presigned_url(self, mock_presign):
        self.client.force_authenticate(self.user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['url'], 'https://signed.example/audio')
        mock_presign.assert_called_once_with(self.answer.audio_key)

    def test_other_user_cannot_request_presigned_url(self):
        self.client.force_authenticate(self.other_user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_answer_without_audio_returns_not_found(self):
        self.answer.audio_key = None
        self.answer.save(update_fields=('audio_key',))
        self.client.force_authenticate(self.user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
