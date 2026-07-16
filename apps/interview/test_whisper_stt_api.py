from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.services.whisper_stt_service import (
    STTAnswerQualityError,
    WhisperTranscription,
    build_stt_stats,
    transcribe_uploaded_audio,
    validate_stt_answer_quality,
)
from apps.interview.models import InterviewQuestion, InterviewSession


class MVPWhisperTranscribeAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='voice-stt@example.com',
            password='password123',
            name='Voice STT',
        )
        self.client.force_authenticate(self.user)
        self.url = reverse('mvp-stt-transcribe')
        self.session = InterviewSession.objects.create(
            user=self.user, interview_type='technical', persona='coach', interview_mode='voice'
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session, order_index=1, question_text='테스트 질문'
        )

    def payload(self, **extra):
        return {
            'audio': self.webm_file(),
            'session_id': str(self.session.id),
            **extra,
        }

    def webm_file(self):
        return SimpleUploadedFile(
            'answer.webm',
            b'fake-webm-audio',
            content_type='audio/webm',
        )

    def test_authentication_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(self.url, self.payload(), format='multipart')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_audio_returns_bad_request(self):
        response = self.client.post(self.url, {}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('audio', response.data)

    def test_unsupported_audio_type_returns_bad_request(self):
        audio = SimpleUploadedFile('answer.mp3', b'audio', content_type='audio/mpeg')

        response = self.client.post(self.url, {'audio': audio}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('audio', response.data)

    @patch('apps.interview.mvp_views.upload_interview_audio', return_value='interview-audio/test.webm')
    @patch('apps.interview.mvp_views.transcribe_uploaded_audio')
    def test_whisper_transcribe_returns_stats(self, mock_transcribe, mock_upload):
        mock_transcribe.return_value = {
            'stt_text': '안녕하세요 음 저는 지원자입니다',
            'speech_duration': 3.2,
            'total_pause_duration': 1.1,
            'long_pause_count': 0,
            'processing_time_ms': 1200,
            'debug': {
                'audio_duration': 5.1,
                'pause_count': 1,
                'first_speech_start_sec': 0.2,
                'filler_words': {'음': 1, '어': 0, '아': 0},
                'words': [],
            },
        }

        response = self.client.post(self.url, self.payload(), format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stt_text'], '안녕하세요 음 저는 지원자입니다')
        self.assertEqual(response.data['speech_duration'], 3.2)
        self.assertEqual(response.data['debug']['pause_count'], 1)
        self.assertEqual(response.data['audio_key'], 'interview-audio/test.webm')
        mock_transcribe.assert_called_once()
        mock_upload.assert_called_once()


class WhisperSTTServiceTests(APITestCase):
    def webm_file(self):
        return SimpleUploadedFile(
            'answer.webm',
            b'fake-webm-audio',
            content_type='audio/webm',
        )

    def test_build_stt_stats_calculates_word_gaps_and_pauses(self):
        stats = build_stt_stats(
            [
                {'word': '음', 'start': 0.1, 'end': 0.3},
                {'word': '안녕하세요', 'start': 0.8, 'end': 1.2},
                {'word': '어', 'start': 4.5, 'end': 4.7},
            ],
            duration=5.0,
        )

        self.assertEqual(stats['audio_duration'], 5.0)
        self.assertEqual(stats['first_speech_start_sec'], 0.1)
        self.assertEqual(stats['speech_duration'], 0.8)
        self.assertEqual(stats['total_pause_duration'], 3.8)
        self.assertEqual(stats['pause_count'], 2)
        self.assertEqual(stats['long_pause_count'], 1)
        self.assertEqual(stats['filler_words'], {'음': 1, '어': 1, '아': 0})
        self.assertEqual(stats['words'][0]['gap'], 0.5)

    @patch('apps.interview.services.whisper_stt_service.os.remove')
    @patch('apps.interview.services.whisper_stt_service.os.path.exists', return_value=True)
    @patch('apps.interview.services.whisper_stt_service.write_upload_to_tempfile', return_value='temp-answer.webm')
    @patch('apps.interview.services.whisper_stt_service.call_whisper')
    def test_temporary_file_is_removed_after_success(self, mock_call, mock_write, mock_exists, mock_remove):
        mock_call.return_value = WhisperTranscription(
            text='테스트 답변입니다',
            words=[
                {'word': '테스트', 'start': 0.0, 'end': 0.7},
                {'word': '답변입니다', 'start': 0.8, 'end': 1.5},
            ],
            duration=1.8,
        )

        transcribe_uploaded_audio(self.webm_file(), language='ko')

        mock_remove.assert_called_once()

    def test_stt_answer_quality_rejects_short_answer(self):
        with self.assertRaises(STTAnswerQualityError):
            validate_stt_answer_quality('네', speech_duration=0.4)

    @patch('apps.interview.services.whisper_stt_service.os.remove')
    @patch('apps.interview.services.whisper_stt_service.os.path.exists', return_value=True)
    @patch('apps.interview.services.whisper_stt_service.write_upload_to_tempfile', return_value='temp-answer.webm')
    @patch('apps.interview.services.whisper_stt_service.call_whisper')
    def test_temporary_file_is_removed_after_failure(self, mock_call, mock_write, mock_exists, mock_remove):
        mock_call.side_effect = RuntimeError('boom')

        with self.assertRaises(RuntimeError):
            transcribe_uploaded_audio(self.webm_file(), language='ko')

        mock_remove.assert_called_once()
