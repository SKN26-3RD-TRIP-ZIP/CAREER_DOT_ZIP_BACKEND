from django.urls import path

from .views import (
    PersonaActiveTemplateView,
    PersonaListView,
    PromptDefaultVersionView,
    PromptTemplateDeleteView,
    PromptTemplateListCreateView,
    PromptVersionListCreateView,
)


urlpatterns = [
    path('personas', PersonaListView.as_view(), name='admin-persona-list'),
    path(
        'personas/<int:persona_id>/active-template',
        PersonaActiveTemplateView.as_view(),
        name='admin-persona-active-template',
    ),
    path(
        'prompt-templates',
        PromptTemplateListCreateView.as_view(),
        name='admin-prompt-template-list-create',
    ),
    path(
        'prompt-templates/<int:template_id>',
        PromptTemplateDeleteView.as_view(),
        name='admin-prompt-template-delete',
    ),
    path(
        'prompt-templates/<int:template_id>/versions',
        PromptVersionListCreateView.as_view(),
        name='admin-prompt-version-list-create',
    ),
    path(
        'prompt-templates/<int:template_id>/default-version',
        PromptDefaultVersionView.as_view(),
        name='admin-prompt-default-version',
    ),
]
