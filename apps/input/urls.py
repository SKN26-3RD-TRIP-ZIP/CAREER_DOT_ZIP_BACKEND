from django.urls import path
from .views import JDListCreateView, JDDetailView, UserProfileView

urlpatterns = [
    path('jds', JDListCreateView.as_view(), name='jd-list-create'),
    path('jds/<uuid:jd_id>', JDDetailView.as_view(), name='jd-detail'),
    path('users/me/profile', UserProfileView.as_view(), name='user-profile'),
]
