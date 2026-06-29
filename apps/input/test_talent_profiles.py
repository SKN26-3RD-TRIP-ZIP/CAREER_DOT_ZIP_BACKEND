from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.input.models import (
    JDTalentProfile,
    JDTalentProfileItem,
    JobDescription,
    TalentProfileCategory,
    TalentProfileTrait,
)
from apps.input.services.talent_profile_service import resolve_effective_talent_profile
from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession
from apps.interview.services.follow_up_generator import _build_document_context
from apps.interview.services.question_generator import _build_job_description_source


def _user(email):
    return User.objects.create_user(
        email=email,
        password='Password123!',
        name=email.split('@')[0],
        is_verified=True,
    )


class TalentProfileAPITests(APITestCase):
    def setUp(self):
        self.owner = _user('talent-owner@example.com')
        self.other = _user('talent-other@example.com')
        self.client.force_authenticate(self.owner)
        self.jd = JobDescription.objects.create(
            user=self.owner,
            company_name='Career.zip',
            position='Backend Developer',
            original_text='JD text',
            talent_profile='AI extracted ownership and collaboration',
        )
        self.other_jd = JobDescription.objects.create(
            user=self.other,
            company_name='Other',
            position='Frontend',
            original_text='Other JD',
        )

    def test_catalog_active_sorted_and_inactive_excluded(self):
        inactive_category = TalentProfileCategory.objects.create(
            category_code='INACTIVE_CATEGORY',
            category_name='Inactive',
            short_description='Inactive category',
            display_order=0,
            is_active=False,
        )
        TalentProfileTrait.objects.create(
            category=inactive_category,
            trait_code='INACTIVE_CATEGORY_TRAIT',
            trait_name='Inactive',
            short_description='Inactive trait',
            display_order=1,
        )
        category = TalentProfileCategory.objects.get(category_code='EXECUTION_RESPONSIBILITY')
        inactive_trait = TalentProfileTrait.objects.create(
            category=category,
            trait_code='INACTIVE_TRAIT',
            trait_name='Inactive trait',
            short_description='Inactive trait',
            display_order=0,
            is_active=False,
        )

        res = self.client.get('/api/v1/talent-profiles/catalog')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        categories = res.data['categories']
        self.assertGreaterEqual(len(categories), 8)
        self.assertEqual(
            [c['display_order'] for c in categories],
            sorted(c['display_order'] for c in categories),
        )
        self.assertNotIn('INACTIVE_CATEGORY', [c['category_code'] for c in categories])
        execution = next(c for c in categories if c['category_code'] == 'EXECUTION_RESPONSIBILITY')
        self.assertNotIn(inactive_trait.trait_code, [t['trait_code'] for t in execution['traits']])
        self.assertEqual(
            [t['display_order'] for t in execution['traits']],
            sorted(t['display_order'] for t in execution['traits']),
        )

    def test_get_missing_profile_returns_null_profile(self):
        res = self.client.get(f'/api/v1/jds/{self.jd.id}/talent-profile')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['jd_id'], str(self.jd.id))
        self.assertIsNone(res.data['profile'])

    def test_other_user_access_denied(self):
        get_res = self.client.get(f'/api/v1/jds/{self.other_jd.id}/talent-profile')
        put_res = self.client.put(
            f'/api/v1/jds/{self.other_jd.id}/talent-profile',
            self._payload(['OWNERSHIP']),
            format='json',
        )

        self.assertEqual(get_res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(put_res.status_code, status.HTTP_404_NOT_FOUND)

    def test_save_draft_and_confirmed_profile(self):
        draft = self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP'], confirmed=False),
            format='json',
        )
        self.assertEqual(draft.status_code, status.HTTP_200_OK)
        self.assertFalse(draft.data['confirmed_by_user'])
        self.assertIsNone(draft.data['confirmed_at'])

        confirmed = self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP', 'PROBLEM_SOLVING', 'COLLABORATION'], confirmed=True),
            format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.assertTrue(confirmed.data['confirmed_by_user'])
        self.assertIsNotNone(confirmed.data['confirmed_at'])
        self.assertEqual([i['priority_order'] for i in confirmed.data['items']], [1, 2, 3])

    def test_one_and_five_items_save_success(self):
        one = self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP']),
            format='json',
        )
        five = self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP', 'ACCOUNTABILITY', 'EXECUTION_SPEED', 'RESULT_ORIENTATION', 'PROBLEM_SOLVING']),
            format='json',
        )

        self.assertEqual(one.status_code, status.HTTP_200_OK)
        self.assertEqual(five.status_code, status.HTTP_200_OK)
        self.assertEqual(len(five.data['items']), 5)

    def test_validation_failures(self):
        cases = [
            {**self._payload([]), 'items': []},
            self._payload(['OWNERSHIP', 'ACCOUNTABILITY', 'EXECUTION_SPEED', 'RESULT_ORIENTATION', 'PROBLEM_SOLVING', 'ANALYTICAL_THINKING']),
            {**self._payload(['OWNERSHIP', 'OWNERSHIP'])},
            {**self._payload(['OWNERSHIP', 'PROBLEM_SOLVING'], priorities=[1, 1])},
            {**self._payload(['OWNERSHIP', 'PROBLEM_SOLVING', 'COLLABORATION'], priorities=[1, 3, 5])},
            self._payload(['NO_SUCH_TRAIT']),
            self._payload(['OWNERSHIP'], descriptions=['x' * 501]),
            {**self._payload(['OWNERSHIP']), 'source_type': 'BAD'},
        ]
        inactive = TalentProfileTrait.objects.get(trait_code='OWNERSHIP')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        cases.append(self._payload(['OWNERSHIP']))

        for payload in cases:
            with self.subTest(payload=payload):
                res = self.client.put(f'/api/v1/jds/{self.jd.id}/talent-profile', payload, format='json')
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replace_success_and_failed_replace_rolls_back(self):
        ok = self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP', 'PROBLEM_SOLVING']),
            format='json',
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

        bad = self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['COLLABORATION', 'NO_SUCH_TRAIT']),
            format='json',
        )

        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        profile = self.jd.custom_talent_profile
        self.assertEqual(
            list(profile.items.order_by('priority_order').values_list('trait__trait_code', flat=True)),
            ['OWNERSHIP', 'PROBLEM_SOLVING'],
        )

    def test_cascade_and_protect(self):
        self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP']),
            format='json',
        )
        trait = TalentProfileTrait.objects.get(trait_code='OWNERSHIP')
        with self.assertRaises(ProtectedError):
            trait.delete()

        profile_id = self.jd.custom_talent_profile.pk
        self.jd.delete()
        self.assertFalse(JDTalentProfile.objects.filter(pk=profile_id).exists())
        self.assertFalse(JDTalentProfileItem.objects.filter(jd_talent_profile_id=profile_id).exists())

    def test_effective_profile_priority_and_fallbacks(self):
        self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP'], confirmed=False),
            format='json',
        )
        draft_effective = resolve_effective_talent_profile(self.jd)
        self.assertEqual(draft_effective['source_type'], 'AI_EXTRACTED')

        self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP'], confirmed=True),
            format='json',
        )
        self.jd.refresh_from_db()
        confirmed_effective = resolve_effective_talent_profile(self.jd)
        self.assertEqual(confirmed_effective['source_type'], 'USER_DEFINED')
        self.assertIn('면접 연습', confirmed_effective['prompt_notice'])

        empty_jd = JobDescription.objects.create(
            user=self.owner,
            company_name='Empty',
            position='Backend',
            original_text='text',
        )
        self.assertEqual(resolve_effective_talent_profile(empty_jd)['summary'], '')

    def test_question_and_followup_context_include_user_notice(self):
        self.client.put(
            f'/api/v1/jds/{self.jd.id}/talent-profile',
            self._payload(['OWNERSHIP'], confirmed=True),
            format='json',
        )
        self.jd.refresh_from_db()
        session = InterviewSession.objects.create(
            user=self.owner,
            jd=self.jd,
            interview_type='personality',
            persona='practical',
        )
        source = _build_job_description_source(session)
        self.assertIn('effective_talent_profile', source)
        self.assertIn('면접 연습', source['talent_profile_prompt_notice'])

        question = InterviewQuestion.objects.create(
            session=session,
            order_index=1,
            question_text='Tell me about ownership.',
            source_type='jd',
        )
        answer = InterviewAnswer.objects.create(
            session=session,
            question=question,
            answer_text='I found and solved a problem.',
        )
        context = _build_document_context(answer)
        self.assertIn('면접 연습', context)
        self.assertIn('OWNERSHIP', context)

    def _payload(self, trait_codes, confirmed=True, priorities=None, descriptions=None):
        priorities = priorities or list(range(1, len(trait_codes) + 1))
        descriptions = descriptions or [''] * len(trait_codes)
        return {
            'source_type': 'USER_DEFINED',
            'source_text': None,
            'custom_summary': '사용자가 면접 연습을 위해 설정한 인재상 기준',
            'confirmed_by_user': confirmed,
            'items': [
                {
                    'trait_code': code,
                    'priority_order': priorities[index],
                    'custom_description': descriptions[index],
                }
                for index, code in enumerate(trait_codes)
            ],
        }
