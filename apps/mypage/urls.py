from django.urls import path

from .views import InterviewHistoryView


urlpatterns = [
    path('interviews', InterviewHistoryView.as_view(), name='mypage-interview-history'),
]
