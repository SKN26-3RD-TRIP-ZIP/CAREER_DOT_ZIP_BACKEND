from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PersonaConfig, PromptTemplate, PromptVersion


class PromptAdminAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            email='prompt-admin@example.com',
            password='password123',
            name='Admin',
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            email='prompt-user@example.com',
            password='password123',
            name='User',
        )
        self.persona = PersonaConfig.objects.create(persona_type='coach')
        self.client.force_authenticate(self.admin_user)

    def test_regular_user_is_forbidden(self):
        self.client.force_authenticate(self.regular_user)

        response = self.client.get(reverse('admin-persona-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_template_and_filter_list(self):
        response = self.client.post(
            reverse('admin-prompt-template-list-create'),
            {
                'persona_config_id': self.persona.id,
                'title': 'Question prompt',
                'prompt_type': 'question_generation',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        list_response = self.client.get(
            reverse('admin-prompt-template-list-create'),
            {'persona_type': 'coach', 'prompt_type': 'question_generation'},
        )
        self.assertEqual(list_response.data['total'], 1)

    def test_versions_auto_increment_and_first_becomes_default(self):
        template = PromptTemplate.objects.create(
            persona_config=self.persona,
            title='Question prompt',
            prompt_type='question_generation',
        )
        url = reverse(
            'admin-prompt-version-list-create',
            kwargs={'template_id': template.id},
        )

        first = self.client.post(url, {'content': 'Version 1'}, format='json')
        second = self.client.post(url, {'content': 'Version 2'}, format='json')

        self.assertEqual(first.data['version_number'], 1)
        self.assertEqual(second.data['version_number'], 2)
        template.refresh_from_db()
        self.assertEqual(template.default_version_id, first.data['prompt_ver_id'])

    def test_relationship_validation_and_soft_delete_guard(self):
        template = PromptTemplate.objects.create(
            persona_config=self.persona,
            title='Question prompt',
            prompt_type='question_generation',
        )
        other_persona = PersonaConfig.objects.create(persona_type='practical')
        other_template = PromptTemplate.objects.create(
            persona_config=other_persona,
            title='Other prompt',
            prompt_type='question_generation',
        )
        version = PromptVersion.objects.create(
            template=other_template,
            version_number=1,
            content='Other version',
        )

        invalid_active = self.client.patch(
            reverse('admin-persona-active-template', kwargs={'persona_id': self.persona.id}),
            {'active_template_id': other_template.id},
            format='json',
        )
        invalid_default = self.client.patch(
            reverse('admin-prompt-default-version', kwargs={'template_id': template.id}),
            {'default_version_id': version.id},
            format='json',
        )
        self.persona.active_template = template
        self.persona.save()
        blocked_delete = self.client.delete(
            reverse('admin-prompt-template-delete', kwargs={'template_id': template.id})
        )

        self.assertEqual(invalid_active.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_default.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(blocked_delete.status_code, status.HTTP_400_BAD_REQUEST)
