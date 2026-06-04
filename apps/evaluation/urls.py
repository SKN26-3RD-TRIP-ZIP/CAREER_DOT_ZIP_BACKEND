from django.urls import path
from .views import (
    EvaluationCreateView,
    EvaluationDetailView,
    WeaknessTagsView,
    StrengthTagsView,
)

urlpatterns = [
    path('evaluations', EvaluationCreateView.as_view(), name='evaluation-create'),
    path('evaluations/<uuid:answer_id>', EvaluationDetailView.as_view(), name='evaluation-detail'),
    path('evaluations/<uuid:answer_id>/weakness-tags', WeaknessTagsView.as_view(), name='weakness-tags'),
    path('evaluations/<uuid:answer_id>/strength-tags', StrengthTagsView.as_view(), name='strength-tags'),
]
