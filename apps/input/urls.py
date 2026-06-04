from django.urls import path
from .views import JDListCreateView, JDDetailView

urlpatterns = [
    path('jds', JDListCreateView.as_view(), name='jd-list-create'),
    path('jds/<uuid:jd_id>', JDDetailView.as_view(), name='jd-detail'),
]
