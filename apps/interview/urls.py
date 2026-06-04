from django.urls import path
from .views import (
    InterviewSessionListCreateView,
    InterviewSessionDetailView,
    InterviewSessionStatusUpdateView,
)

urlpatterns = [
    path('sessions', InterviewSessionListCreateView.as_view(), name='interview-session-list-create'),
    path('sessions/<uuid:session_id>', InterviewSessionDetailView.as_view(), name='interview-session-detail'),
    path('sessions/<uuid:session_id>/status', InterviewSessionStatusUpdateView.as_view(), name='interview-session-status-update'),
]
