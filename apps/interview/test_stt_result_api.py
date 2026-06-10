from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession


class MVPSTTResultUpdateAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='stt-owner@example.com',
            password='password123',
            name='STT Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='stt-other@example.com',
            password='password123',
            name='STT Other',
        )
        self.client.force_authenticate(self.user)

        self.session = InterviewSession.objects.create(
            user=self.user,
            interview_type='technical',
            persona='practical',
            interview_mode='voice',
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type='main',
            question_text='Explain your backend project.',
            source_type='general',
        )
        self.answer = InterviewAnswer.objects.create(
            session=self.session,
            question=self.question,
            answer_text='초기 답변입니다.',
            answer_source='text',
        )

        self.other_session = InterviewSession.objects.create(
            user=self.other_user,
            interview_type='technical',
            persona='practical',
            interview_mode='voice',
        )
        self.other_question = InterviewQuestion.objects.create(
            session=self.other_session,
            order_index=1,
            question_type='main',
            question_text='Other question.',
            source_type='general',
        )
        self.other_answer = InterviewAnswer.objects.create(
            session=self.other_session,
            question=self.other_question,
            answer_text='Other answer.',
            answer_source='text',
        )

    def stt_url(self, answer=None):
        target = answer or self.answer
        return reverse('mvp-answer-stt-update', kwargs={'answer_id': target.id})

    def test_update_stt_result_returns_ok(self):
        payload = {
            'stt_text': 'STT로 변환된 답변입니다.',
            'audio_url': None,
            'speech_duration': 45.25,
            'total_pause_duration': 4.12,
            'long_pause_count': 1,
        }

        response = self.client.patch(self.stt_url(), payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['answer_id'], str(self.answer.id))
        self.assertEqual(response.data['stt_text'], payload['stt_text'])

        self.answer.refresh_from_db()
        self.assertEqual(self.answer.stt_text, payload['stt_text'])
        self.assertEqual(self.answer.answer_text, payload['stt_text'])
        self.assertEqual(self.answer.answer_source, 'stt')
        self.assertEqual(self.answer.audio_url, None)
        self.assertEqual(self.answer.speech_duration, payload['speech_duration'])
        self.assertEqual(self.answer.total_pause_duration, payload['total_pause_duration'])
        self.assertEqual(self.answer.long_pause_count, payload['long_pause_count'])

    def test_blank_stt_text_returns_bad_request(self):
        response = self.client.patch(
            self.stt_url(),
            {'stt_text': '   '},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_users_answer_returns_not_found(self):
        response = self.client.patch(
            self.stt_url(self.other_answer),
            {'stt_text': '다른 사용자 답변 수정 시도'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authentication_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.patch(
            self.stt_url(),
            {'stt_text': '인증 없는 요청'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
