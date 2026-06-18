from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PersonaConfig, PromptTemplate, PromptVersion
from .services import get_runtime_prompt_version


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


class RuntimePromptServiceTests(APITestCase):
    def test_active_template_default_version_has_priority(self):
        persona = PersonaConfig.objects.create(persona_type='practical')
        normal_template = PromptTemplate.objects.create(
            persona_config=persona,
            title='Normal prompt',
            prompt_type='question_generation',
        )
        normal_version = PromptVersion.objects.create(
            template=normal_template,
            version_number=1,
            content='normal prompt',
        )
        normal_template.default_version = normal_version
        normal_template.save(update_fields=('default_version', 'updated_at'))

        active_template = PromptTemplate.objects.create(
            persona_config=persona,
            title='Active prompt',
            prompt_type='question_generation',
        )
        active_version = PromptVersion.objects.create(
            template=active_template,
            version_number=1,
            content='active prompt',
        )
        active_template.default_version = active_version
        active_template.save(update_fields=('default_version', 'updated_at'))
        persona.active_template = active_template
        persona.save(update_fields=('active_template', 'updated_at'))

        result = get_runtime_prompt_version('practical', 'question_generation')

        self.assertEqual(result.version_id, active_version.id)
        self.assertEqual(result.content, 'active prompt')

    def test_matching_active_template_default_version_is_used_without_active_persona_template(self):
        persona = PersonaConfig.objects.create(persona_type='practical')
        template = PromptTemplate.objects.create(
            persona_config=persona,
            title='Answer prompt',
            prompt_type='answer_evaluation',
        )
        version = PromptVersion.objects.create(
            template=template,
            version_number=1,
            content='answer prompt',
        )
        template.default_version = version
        template.save(update_fields=('default_version', 'updated_at'))

        result = get_runtime_prompt_version('practical', 'answer_evaluation')

        self.assertEqual(result.version_id, version.id)
        self.assertEqual(result.content, 'answer prompt')

    def test_returns_none_when_no_matching_prompt_exists(self):
        PersonaConfig.objects.create(persona_type='practical')

        result = get_runtime_prompt_version('practical', 'follow_up_generation')

        self.assertIsNone(result)


class SeedInterviewPromptsCommandTests(APITestCase):
    def test_seed_interview_prompts_is_idempotent_and_runtime_ready(self):
        out = StringIO()
        call_command('seed_interview_prompts', stdout=out)

        self.assertEqual(PersonaConfig.objects.count(), 3)
        self.assertEqual(PromptTemplate.objects.count(), 9)
        self.assertEqual(PromptVersion.objects.count(), 9)

        for persona_type in ('coach', 'practical', 'verifier'):
            persona = PersonaConfig.objects.get(persona_type=persona_type)
            self.assertIsNotNone(persona.active_template_id)
            self.assertEqual(persona.active_template.prompt_type, 'question_generation')
            for prompt_type in (
                'question_generation',
                'answer_evaluation',
                'follow_up_generation',
            ):
                runtime_prompt = get_runtime_prompt_version(persona_type, prompt_type)
                self.assertIsNotNone(runtime_prompt)
                self.assertIn('반드시 JSON object만 반환하세요.', runtime_prompt.content)

        question_prompt = get_runtime_prompt_version('coach', 'question_generation')
        self.assertIn('question_text', question_prompt.content)
        self.assertIn('question_category', question_prompt.content)
        self.assertIn('source_tags', question_prompt.content)
        self.assertIn('한국어 면접 질문', question_prompt.content)

        answer_prompt = get_runtime_prompt_version('coach', 'answer_evaluation')
        self.assertIn('selected_weakness_tag', answer_prompt.content)
        self.assertIn('next_action', answer_prompt.content)

        followup_prompt = get_runtime_prompt_version('coach', 'follow_up_generation')
        self.assertIn('followup_question', followup_prompt.content)
        self.assertIn('selected_weakness_tag', followup_prompt.content)

        first_template_ids = set(PromptTemplate.objects.values_list('id', flat=True))
        first_version_ids = set(PromptVersion.objects.values_list('id', flat=True))

        out = StringIO()
        call_command('seed_interview_prompts', stdout=out)

        self.assertEqual(PersonaConfig.objects.count(), 3)
        self.assertEqual(PromptTemplate.objects.count(), 9)
        self.assertEqual(PromptVersion.objects.count(), 9)
        self.assertEqual(first_template_ids, set(PromptTemplate.objects.values_list('id', flat=True)))
        self.assertEqual(first_version_ids, set(PromptVersion.objects.values_list('id', flat=True)))

    def test_seed_reuses_existing_persona_prompt_type_template(self):
        persona = PersonaConfig.objects.create(persona_type='coach')
        template = PromptTemplate.objects.create(
            persona_config=persona,
            title='코치형 템플릿 1',
            prompt_type='question_generation',
        )
        version = PromptVersion.objects.create(
            template=template,
            version_number=1,
            content='코치형 템플릿 1',
        )
        template.default_version = version
        template.save(update_fields=('default_version', 'updated_at'))
        persona.active_template = template
        persona.save(update_fields=('active_template', 'updated_at'))

        call_command('seed_interview_prompts', stdout=StringIO())

        persona.refresh_from_db()
        template.refresh_from_db()
        version.refresh_from_db()

        self.assertEqual(
            PromptTemplate.objects.filter(
                persona_config=persona,
                prompt_type='question_generation',
            ).count(),
            1,
        )
        self.assertEqual(persona.active_template_id, template.id)
        self.assertEqual(template.title, '기본 면접 질문 생성 프롬프트 (coach)')
        self.assertTrue(template.is_active)
        self.assertEqual(template.default_version_id, version.id)
        self.assertIn('반드시 JSON object만 반환하세요.', version.content)
        self.assertIn('question_category', version.content)

    def test_seed_dedupe_deactivates_duplicate_templates_in_seed_scope(self):
        persona = PersonaConfig.objects.create(persona_type='coach')
        keep_template = PromptTemplate.objects.create(
            persona_config=persona,
            title='활성 질문 템플릿',
            prompt_type='question_generation',
            is_active=True,
        )
        keep_version = PromptVersion.objects.create(
            template=keep_template,
            version_number=1,
            content='활성 질문 템플릿',
        )
        keep_template.default_version = keep_version
        keep_template.save(update_fields=('default_version', 'updated_at'))
        duplicate_template = PromptTemplate.objects.create(
            persona_config=persona,
            title='Seed Interview Question Generation (coach)',
            prompt_type='question_generation',
            is_active=True,
        )
        PromptVersion.objects.create(
            template=duplicate_template,
            version_number=1,
            content='old english prompt',
        )
        persona.active_template = keep_template
        persona.save(update_fields=('active_template', 'updated_at'))

        call_command('seed_interview_prompts', '--dedupe', stdout=StringIO())

        keep_template.refresh_from_db()
        duplicate_template.refresh_from_db()
        persona.refresh_from_db()

        self.assertTrue(keep_template.is_active)
        self.assertFalse(duplicate_template.is_active)
        self.assertEqual(persona.active_template_id, keep_template.id)
        self.assertEqual(
            PromptTemplate.objects.filter(
                persona_config=persona,
                prompt_type='question_generation',
                is_active=True,
            ).count(),
            1,
        )
        runtime_prompt = get_runtime_prompt_version('coach', 'question_generation')
        self.assertEqual(runtime_prompt.version_id, keep_template.default_version_id)
        self.assertIn('반드시 JSON object만 반환하세요.', runtime_prompt.content)
