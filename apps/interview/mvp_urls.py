from django.urls import path

from .mvp_views import (
    MVPQuestionGenerateView,
    MVPQuestionListView,
    MVPPracticeSessionCreateView,
    MVPAnswerCreateView,
    MVPFollowupQuestionCreateView,
    MVPSTTResultUpdateView,
    MVPSessionCreateView,
    MVPSessionDetailView,
    MVPSessionStatusView,
    MVPTTSSpeechView,
    MVPWhisperDevTranscribeView,
    MVPWhisperTranscribeView,
)


# MVP 음성 면접 플로우에서 프론트가 호출하는 세션/질문/답변/STT/TTS API 라우트 모음.
urlpatterns = [
    # 면접 세션 생성, 상세 조회, 완료 상태 변경에 사용한다.
    path('sessions', MVPSessionCreateView.as_view(), name='mvp-session-create'),
    path('sessions/<uuid:session_id>', MVPSessionDetailView.as_view(), name='mvp-session-detail'),
    path('sessions/<uuid:session_id>/status', MVPSessionStatusView.as_view(), name='mvp-session-status'),
    path(
        'sessions/<uuid:source_session_id>/practice',
        MVPPracticeSessionCreateView.as_view(),
        name='mvp-practice-session-create',
    ),

    # 세션에 연결된 JD/이력서/프로젝트 기반 질문 생성 및 질문 목록 조회.
    path(
        'sessions/<uuid:session_id>/questions/generate',
        MVPQuestionGenerateView.as_view(),
        name='mvp-question-generate',
    ),
    path(
        'sessions/<uuid:session_id>/questions',
        MVPQuestionListView.as_view(),
        name='mvp-question-list',
    ),

    # 답변 생성 후 STT 분석값을 같은 답변에 patch하고, 필요하면 꼬리질문을 생성한다.
    path('answers', MVPAnswerCreateView.as_view(), name='mvp-answer-create'),
    path(
        'answers/<uuid:answer_id>/stt',
        MVPSTTResultUpdateView.as_view(),
        name='mvp-answer-stt-update',
    ),
    path(
        'answers/<uuid:answer_id>/followup',
        MVPFollowupQuestionCreateView.as_view(),
        name='mvp-answer-followup-create',
    ),

    # 브라우저 녹음 파일을 Whisper STT로 변환하고, 질문 텍스트를 TTS mp3로 합성한다.
    path('stt/transcribe', MVPWhisperTranscribeView.as_view(), name='mvp-stt-transcribe'),
    path('stt/transcribe/dev', MVPWhisperDevTranscribeView.as_view(), name='mvp-stt-transcribe-dev'),
    path('tts/speech', MVPTTSSpeechView.as_view(), name='mvp-tts-speech'),
]
