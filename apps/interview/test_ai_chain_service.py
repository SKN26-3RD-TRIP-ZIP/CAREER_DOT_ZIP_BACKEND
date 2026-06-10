from django.test import SimpleTestCase

from apps.interview.ai_chain_contracts import NextAction
from apps.interview.services.ai_chain_service import InterviewAIChainService


class InterviewAIChainServiceTest(SimpleTestCase):
    def setUp(self):
        self.service = InterviewAIChainService()

    def test_judge_answer_sufficiency_returns_followup_when_answer_is_insufficient(self):
        payload = {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "question": {
                "question_id": "22222222-2222-2222-2222-222222222222",
                "question_text": "프로젝트에서 본인이 맡은 역할과 기술 선택 이유를 설명해주세요.",
                "question_type": "technical",
                "parent_question_id": None,
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

        result = self.service.judge_answer_sufficiency(payload)

        self.assertFalse(result["is_sufficient"])
        self.assertTrue(result["should_generate_followup"])
        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertIsNotNone(result["selected_weakness_tag"])
        self.assertGreaterEqual(len(result["answer_weakness_tags"]), 1)

    def test_judge_answer_sufficiency_returns_next_question_when_answer_is_sufficient(self):
        payload = {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "question": {
                "question_id": "22222222-2222-2222-2222-222222222222",
                "question_text": "프로젝트에서 본인이 맡은 역할과 기술 선택 이유를 설명해주세요.",
                "question_type": "technical",
                "parent_question_id": None,
                "source_tags": [],
            },
            "answer": {
                "answer_id": "33333333-3333-3333-3333-333333333333",
                "answer_text": (
                    "제가 직접 LangChain 기반 질문 생성 체인을 설계했고, 일반 함수 호출 방식과 비교했을 때 "
                    "프롬프트 단계 분리와 추후 RAG 검색 결과 연결이 쉬웠기 때문에 선택했습니다. "
                    "또한 답변 평가와 꼬리질문 생성을 분리해 유지보수성과 확장성을 높이는 것을 기준으로 판단했습니다."
                ),
            },
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "",
            },
            "prompt_version_id": 1,
        }

        result = self.service.judge_answer_sufficiency(payload)

        self.assertTrue(result["is_sufficient"])
        self.assertFalse(result["should_generate_followup"])
        self.assertEqual(result["next_action"], NextAction.NEXT_QUESTION.value)
        self.assertEqual(result["answer_weakness_tags"], [])
        self.assertIsNone(result["selected_weakness_tag"])

    def test_generate_followup_question_uses_selected_weakness_tag(self):
        payload = {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "parent_question": {
                "question_id": "22222222-2222-2222-2222-222222222222",
                "question_text": "프로젝트에서 본인이 맡은 역할과 기술 선택 이유를 설명해주세요.",
                "question_type": "technical",
                "source_tags": [],
            },
            "answer": {
                "answer_id": "33333333-3333-3333-3333-333333333333",
                "answer_text": "데이터를 수집하고 분석해서 리포트를 만들었습니다.",
            },
            "selected_weakness_tag": {
                "answer_weakness_tag_id": "44444444-4444-4444-4444-444444444444",
                "weakness_tag_id": "00000000-0000-0000-0000-000000000002",
                "tag_name": "본인 기여도 불명확",
                "reason": "프로젝트에서 본인이 직접 수행한 역할과 기여가 명확하지 않음",
            },
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "",
            },
            "prompt_version_id": 1,
            "conversation_context": {
                "previous_question_count": 1,
                "previous_followup_count_for_parent": 0,
            },
        }

        result = self.service.generate_followup_question(payload)
        followup = result["followup_question"]

        self.assertEqual(result["session_id"], payload["session_id"])
        self.assertEqual(
            followup["parent_question_id"],
            payload["parent_question"]["question_id"],
        )
        self.assertEqual(
            followup["generated_from_answer_id"],
            payload["answer"]["answer_id"],
        )
        self.assertEqual(
            followup["answer_weakness_tag_id"],
            payload["selected_weakness_tag"]["answer_weakness_tag_id"],
        )
        self.assertIn("본인이 직접", followup["question_text"])

    def test_generate_questions_uses_fallback_when_input_sources_are_empty(self):
        payload = {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "",
            },
            "prompt_version_id": 1,
            "input_sources": {},
            "generation_options": {
                "question_count": 3,
                "allow_multiple_source_tags": True,
            },
        }

        result = self.service.generate_questions(payload)

        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["fallback_reason"], "사용자 입력 자료 부족")
        self.assertEqual(len(result["questions"]), 3)
        self.assertEqual(
            result["questions"][0]["source_tags"][0]["source_type"],
            "question_bank",
        )
