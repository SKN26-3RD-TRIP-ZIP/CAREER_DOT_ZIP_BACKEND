from django.urls import path

from .views import WorknetJobSearchView


urlpatterns = [
    path('worknet/jobs', WorknetJobSearchView.as_view(), name='worknet-job-search'),
]
