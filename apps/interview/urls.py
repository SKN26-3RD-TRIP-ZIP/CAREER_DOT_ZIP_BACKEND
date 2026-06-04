from django.urls import path
from .views import (
    InterviewSessionListCreateView,
    InterviewSessionDetailView,
    InterviewSessionStatusUpdateView,
    InterviewQuestionGenerateView,
    InterviewQuestionListView,
)

urlpatterns = [
    path('sessions', InterviewSessionListCreateView.as_view(), name='interview-session-list-create'),
    path('sessions/<uuid:session_id>', InterviewSessionDetailView.as_view(), name='interview-session-detail'),
    path('sessions/<uuid:session_id>/status', InterviewSessionStatusUpdateView.as_view(), name='interview-session-status-update'),
    path('sessions/<uuid:session_id>/questions/generate', InterviewQuestionGenerateView.as_view(), name='interview-question-generate'),
    path('sessions/<uuid:session_id>/questions', InterviewQuestionListView.as_view(), name='interview-question-list'),
]
