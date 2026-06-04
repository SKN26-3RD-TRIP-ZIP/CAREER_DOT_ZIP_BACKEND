from django.urls import path
from .views import (
    JDListCreateView,
    JDDetailView,
    UserProfileView,
    ResumeMasterCreateView,
    ResumeMasterDetailView,
    ResumeEducationCreateView,
    ResumeCareerCreateView,
    ResumeSkillCreateView,
    ResumeCertificateCreateView,
)

urlpatterns = [
    path('jds', JDListCreateView.as_view(), name='jd-list-create'),
    path('jds/<uuid:jd_id>', JDDetailView.as_view(), name='jd-detail'),
    path('users/me/profile', UserProfileView.as_view(), name='user-profile'),
    path('resumes', ResumeMasterCreateView.as_view(), name='resume-create'),
    path('resumes/<uuid:resume_id>', ResumeMasterDetailView.as_view(), name='resume-detail'),
    path('resumes/<uuid:resume_id>/education', ResumeEducationCreateView.as_view(), name='resume-education-create'),
    path('resumes/<uuid:resume_id>/careers', ResumeCareerCreateView.as_view(), name='resume-career-create'),
    path('resumes/<uuid:resume_id>/skills', ResumeSkillCreateView.as_view(), name='resume-skill-create'),
    path('resumes/<uuid:resume_id>/certificates', ResumeCertificateCreateView.as_view(), name='resume-certificate-create'),
]
