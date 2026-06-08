from django.test import SimpleTestCase

from apps.interview.ai_chain_contracts import NextAction
from apps.interview.services.ai_chain_openai_engine import AIChainOpenAIEngine


class AIChainOpenAIEngineTest(SimpleTestCase):
    def setUp(self):
        self.engine = AIChainOpenAIEngine()

    def test_openai_engine_keeps_mock_fallback_persona_contract(self):
        personas = self.engine.get_personas()

        self.assertGreaterEqual(len(personas), 1)
        self.assertIn("persona_type", personas[0])

    def test_openai_engine_keeps_answer_sufficiency_contract_with_fallback(self):
        payload = {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "question": {
                "question_id": "22222222-2222-2222-2222-222222222222",
                "question_text": "프로젝트에서 본인이 맡은 역할과 기술 선택 이유를 설명해주세요.",
                "question_type": "technical",
                "source_tags": [],
            },
            "answer": {
                "answer_id": "33333333-3333-3333-3333-333333333333",
                "answer_text": "제가 데이터를 수집하고 분석해서 리포트를 만들었습니다.",
            },
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "",
            },
            "prompt_version_id": 1,
        }

        result = self.engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertTrue(result["should_generate_followup"])

    def test_openai_engine_keeps_question_generation_contract_with_fallback(self):
        payload = {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "input_sources": {},
            "generation_options": {
                "question_count": 3,
                "allow_multiple_source_tags": True,
            },
        }

        result = self.engine.generate_questions(payload)

        self.assertTrue(result["fallback_used"])
        self.assertEqual(len(result["questions"]), 3)
