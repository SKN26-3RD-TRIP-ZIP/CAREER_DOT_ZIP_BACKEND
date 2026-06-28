from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from apps.interview.ai_chain_contracts import NextAction
from apps.interview.models import (
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    QuestionSourceTag,
)
from apps.interview.services.ai_chain_service import InterviewAIChainService
from apps.interview.services.follow_up_generator import FollowupGenerator
from apps.interview.services.sufficiency_payload import (
    build_sufficiency_payload_from_answer,
)


@override_settings(
    INTERVIEW_AI_CHAIN_ENGINE='mock',
    INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=False,
)
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
        self.assertIn("question_text", followup)
        self.assertGreater(len(followup["question_text"]), 10)

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


class RecordingSufficiencyEngine:
    def __init__(self, result):
        self.result = result
        self.payload = None

    def judge_answer_sufficiency(self, payload):
        self.payload = payload
        return self.result


class EvaluateAnswerSufficiencyPublicInterfaceTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            email="sufficiency-interface@example.com",
            password="password123",
            name="Sufficiency Interface",
        )
        self.session = InterviewSession.objects.create(
            user=user,
            interview_type="technical",
            persona="practical",
            interview_mode="text",
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type="main",
            question_category="technical",
            question_text="Explain your API transaction design.",
            source_type="resume",
            source_reference="Django API project",
        )
        self.answer = InterviewAnswer.objects.create(
            session=self.session,
            question=self.question,
            answer_text="Text answer",
            stt_text="Voice STT answer",
        )
        QuestionSourceTag.objects.create(
            question=self.question,
            source_type="resume",
            source_label="expected_technical_keywords",
            source_text_excerpt="transaction, atomicity, rollback",
            source_reference="test:technical-keywords",
        )

    def test_evaluate_answer_sufficiency_builds_payload_and_normalizes_result(self):
        engine = RecordingSufficiencyEngine(
            {
                "answer_weakness_tags": [
                    {
                        "tag_name": "TECH_DEPTH_LOW",
                        "reason": "More technical detail is needed.",
                    }
                ],
                "selected_weakness_tag": {
                    "tag_name": "TECH_DEPTH_LOW",
                    "reason": "More technical detail is needed.",
                },
                "next_action": "GENERATE_FOLLOWUP",
            }
        )
        service = InterviewAIChainService(engine=engine)

        result = service.evaluate_answer_sufficiency(self.answer)

        self.assertEqual(
            result,
            {
                "answer_weakness_tags": [
                    {
                        "tag_name": "TECH_DEPTH_LOW",
                        "reason": "More technical detail is needed.",
                    }
                ],
                "selected_weakness_tag": {
                    "tag_name": "TECH_DEPTH_LOW",
                    "reason": "More technical detail is needed.",
                },
            },
        )
        self.assertEqual(engine.payload["answer"]["answer_id"], str(self.answer.id))
        self.assertEqual(engine.payload["answer"]["answer_text"], "Text answer")
        self.assertEqual(engine.payload["question"]["question_id"], str(self.question.id))
        self.assertEqual(engine.payload["interview_type"], "technical")
        self.assertEqual(
            engine.payload["question"]["question_category"],
            "technical",
        )
        self.assertEqual(
            engine.payload["question"]["interview_type"],
            "technical",
        )
        self.assertEqual(
            engine.payload["question"]["expected_technical_keywords"],
            "transaction, atomicity, rollback",
        )

    def test_personality_sufficiency_payload_has_no_technical_keywords(self):
        self.question.question_category = "personality"
        self.question.save(update_fields=("question_category", "updated_at"))

        payload = build_sufficiency_payload_from_answer(self.answer)

        self.assertEqual(payload["question"]["question_category"], "personality")
        self.assertEqual(payload["question"]["expected_technical_keywords"], "")

    def test_followup_payload_preserves_technical_question_context(self):
        payload = FollowupGenerator._build_followup_payload(
            self.answer,
            {
                "tag_name": "NO_ALTERNATIVE",
                "reason": "Alternative comparison is missing.",
            },
        )

        self.assertEqual(payload["interview_type"], "technical")
        self.assertEqual(
            payload["parent_question"]["question_category"],
            "technical",
        )
        self.assertEqual(
            payload["parent_question"]["interview_type"],
            "technical",
        )
        self.assertEqual(
            payload["parent_question"]["expected_technical_keywords"],
            "transaction, atomicity, rollback",
        )
        self.assertEqual(
            payload["followup_context"]["purpose"],
            "alternative_and_tradeoff_comparison",
        )

    def test_sufficiency_and_followup_payloads_include_persona_policy(self):
        expected_personas = {
            "coach": "coach",
            "friendly": "coach",
            "practical": "practical",
            "verifier": "verifier",
            "verify": "verifier",
        }

        for stored_persona, canonical_persona in expected_personas.items():
            self.session.persona = stored_persona
            sufficiency_payload = build_sufficiency_payload_from_answer(self.answer)
            followup_payload = FollowupGenerator._build_followup_payload(
                self.answer,
                {
                    "tag_name": "TECH_DEPTH_LOW",
                    "reason": "More technical detail is needed.",
                },
            )

            for payload in (sufficiency_payload, followup_payload):
                persona = payload["persona"]
                self.assertEqual(persona["persona_type"], canonical_persona)
                self.assertIn("question_focus", persona["policy"])
                self.assertIn("followup_style", persona["policy"])
                self.assertIn("feedback_tone", persona["policy"])
                self.assertIn("verification_depth", persona["policy"])
                self.assertIn("forbidden_tone", persona["policy"])

    def test_comprehensive_session_preserves_each_question_category(self):
        self.session.interview_type = "comprehensive"
        self.session.save(update_fields=("interview_type", "updated_at"))

        technical_payload = build_sufficiency_payload_from_answer(self.answer)
        self.question.question_category = "personality"
        self.question.save(update_fields=("question_category", "updated_at"))
        personality_payload = build_sufficiency_payload_from_answer(self.answer)

        self.assertEqual(technical_payload["interview_type"], "comprehensive")
        self.assertEqual(
            technical_payload["question"]["question_category"],
            "technical",
        )
        self.assertEqual(personality_payload["interview_type"], "comprehensive")
        self.assertEqual(
            personality_payload["question"]["question_category"],
            "personality",
        )

    def test_evaluate_answer_sufficiency_guarantees_empty_contract(self):
        service = InterviewAIChainService(
            engine=RecordingSufficiencyEngine(
                {
                    "answer_weakness_tags": None,
                    "selected_weakness_tag": [],
                }
            )
        )

        result = service.evaluate_answer_sufficiency(self.answer)

        self.assertEqual(
            result,
            {
                "answer_weakness_tags": [],
                "selected_weakness_tag": None,
            },
        )

    def test_evaluate_answer_sufficiency_uses_stt_text_in_voice_mode(self):
        self.session.interview_mode = "voice"
        self.session.save(update_fields=("interview_mode", "updated_at"))
        engine = RecordingSufficiencyEngine({})
        service = InterviewAIChainService(engine=engine)

        service.evaluate_answer_sufficiency(self.answer)

        self.assertEqual(engine.payload["answer"]["answer_text"], "Voice STT answer")

    def test_evaluate_answer_sufficiency_uses_answer_text_without_stt_text(self):
        self.session.interview_mode = "voice"
        self.session.save(update_fields=("interview_mode", "updated_at"))
        self.answer.stt_text = ""
        self.answer.save(update_fields=("stt_text", "updated_at"))
        engine = RecordingSufficiencyEngine({})
        service = InterviewAIChainService(engine=engine)

        service.evaluate_answer_sufficiency(self.answer)

        self.assertEqual(engine.payload["answer"]["answer_text"], "Text answer")
