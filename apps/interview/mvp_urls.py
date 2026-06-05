from django.urls import path

from .mvp_views import (
    MVPQuestionGenerateView,
    MVPQuestionListView,
    MVPAnswerCreateView,
    MVPFollowupQuestionCreateView,
    MVPSessionCreateView,
    MVPSessionDetailView,
    MVPSessionStatusView,
)


urlpatterns = [
    path('sessions', MVPSessionCreateView.as_view(), name='mvp-session-create'),
    path('sessions/<uuid:session_id>', MVPSessionDetailView.as_view(), name='mvp-session-detail'),
    path('sessions/<uuid:session_id>/status', MVPSessionStatusView.as_view(), name='mvp-session-status'),
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
    path('answers', MVPAnswerCreateView.as_view(), name='mvp-answer-create'),
    path(
        'answers/<uuid:answer_id>/followup',
        MVPFollowupQuestionCreateView.as_view(),
        name='mvp-answer-followup-create',
    ),
]
