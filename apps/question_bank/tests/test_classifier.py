from django.test import SimpleTestCase

from apps.question_bank.services.classifier import (
    classify_difficulty,
    classify_question_type,
)
from apps.question_bank.services.keyword_extractor import extract_keywords


class ClassifierTests(SimpleTestCase):
    def test_question_type_rules(self):
        self.assertEqual(classify_question_type('API와 DB 설계를 설명하세요.'), 'technical')
        self.assertEqual(classify_question_type('협업 중 갈등을 해결한 경험은?'), 'personality')
        self.assertEqual(classify_question_type('회사 지원동기는 무엇인가요?'), 'job')

    def test_difficulty_rules(self):
        self.assertEqual(classify_difficulty('아키텍처 설계의 트레이드오프는?', 'technical'), 'hard')
        self.assertEqual(classify_difficulty('자기소개를 해주세요.', 'personality'), 'easy')
        self.assertEqual(classify_difficulty('프로젝트 역할을 설명하세요.', 'job'), 'medium')

    def test_keyword_extraction_preserves_candidate_order_and_removes_duplicates(self):
        keywords = extract_keywords('python API와 Django API, JavaScript를 사용했습니다.')
        self.assertEqual(keywords, ['Python', 'JavaScript', 'Django', 'API'])
        self.assertNotIn('Java', keywords)
