from django.urls import path
from .views import InterviewHistoryView, GrowthView

urlpatterns = [
    path('interviews', InterviewHistoryView.as_view(), name='mypage-interview-history'),
    path('growth', GrowthView.as_view(), name='mypage-growth'),
]
