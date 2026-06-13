from django.urls import path

from .views import WorknetJobSearchView
from .views_jobs import MockJobListView, MockJobDetailView


urlpatterns = [
    path('worknet/jobs', WorknetJobSearchView.as_view(), name='worknet-job-search'),
    path('jobs', MockJobListView.as_view(), name='mock-jobs'),
    path('jobs/<str:job_id>', MockJobDetailView.as_view(), name='mock-job-detail'),
]
