import uuid

from django.test import TestCase

from apps.question_bank.models import QuestionBankItem
from apps.question_bank.services.question_bank_service import get_question_candidates


class QuestionBankServiceTests(TestCase):
    def create_item(self, **overrides):
        defaults = {
            'question_text': '기본 질문',
            'question_type': 'technical',
            'difficulty': 'medium',
            'keywords': [],
            'source_file': f'{QuestionBankItem.objects.count()}.json',
            'source_ref': str(uuid.uuid4()),
        }
        defaults.update(overrides)
        return QuestionBankItem.objects.create(**defaults)

    def test_keyword_matches_are_ranked_first(self):
        self.create_item(question_text='No match', keywords=['Java'])
        matched = self.create_item(question_text='Best match', keywords=['Python', 'API'])
        results = get_question_candidates(['Python'], ['API'])
        self.assertEqual(results[0]['question_bank_id'], str(matched.id))
        self.assertEqual(results[0]['match_score'], 2)

    def test_question_type_difficulty_limit_and_active_filters(self):
        self.create_item(question_text='Technical medium')
        expected = self.create_item(
            question_text='Personality easy',
            question_type='personality',
            difficulty='easy',
        )
        self.create_item(
            question_text='Inactive',
            question_type='personality',
            difficulty='easy',
            is_active=False,
        )
        results = get_question_candidates(
            question_types=['personality'],
            difficulty='easy',
            limit=1,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['question_bank_id'], str(expected.id))
