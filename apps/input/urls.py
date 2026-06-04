from django.urls import path
from .views import (
    JDListCreateView,
    JDDetailView,
    UserProfileView,
    ResumeMasterCreateView,
    ResumeMasterDetailView,
)

urlpatterns = [
    path('jds', JDListCreateView.as_view(), name='jd-list-create'),
    path('jds/<uuid:jd_id>', JDDetailView.as_view(), name='jd-detail'),
    path('users/me/profile', UserProfileView.as_view(), name='user-profile'),
    path('resumes', ResumeMasterCreateView.as_view(), name='resume-create'),
    path('resumes/<uuid:resume_id>', ResumeMasterDetailView.as_view(), name='resume-detail'),
]
