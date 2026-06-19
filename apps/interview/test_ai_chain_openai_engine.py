from django.test import TestCase, override_settings

from apps.interview.ai_chain_contracts import NextAction
from apps.interview.services.ai_chain_openai_engine import (
    AIChainOpenAIEngine,
    AIChainOpenAIError,
)
from apps.prompt.models import PersonaConfig, PromptTemplate, PromptVersion


class FakeOpenAIMessage:
    def __init__(self, content):
        self.content = content


class FakeOpenAIChoice:
    def __init__(self, content):
        self.message = FakeOpenAIMessage(content)


class FakeOpenAIResponse:
    def __init__(self, content):
        self.choices = [FakeOpenAIChoice(content)]


class FakeChatCompletions:
    def __init__(self, content):
        self.content = content
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeOpenAIResponse(self.content)


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeOpenAIClient:
    def __init__(self, content):
        self.completions = FakeChatCompletions(content)
        self.chat = FakeChat(self.completions)


class AIChainOpenAIEngineTest(TestCase):
    def setUp(self):
        self.engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            enable_real_call=False,
        )

    def _question_generation_payload(self):
        return {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "",
            },
            "input_sources": {
                "job_description": {
                    "position": "Backend Developer",
                    "original_text": "Python Django REST API 개발",
                    "job_requirements": "Django API 설계 경험",
                }
            },
            "generation_options": {
                "question_count": 2,
                "allow_multiple_source_tags": True,
            },
        }

    def _sufficiency_payload(self):
        return {
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

    def _followup_payload(self):
        return {
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
                "reason": "본인 기여가 명확하지 않음",
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

    def test_openai_engine_keeps_mock_fallback_persona_contract(self):
        personas = self.engine.get_personas()

        self.assertGreaterEqual(len(personas), 1)
        self.assertIn("persona_type", personas[0])

    def test_openai_engine_uses_real_call_when_enabled_for_question_generation(self):
        raw_response = """```json
        {
          "session_id": "11111111-1111-1111-1111-111111111111",
          "questions": [
            {
              "client_question_key": "q_001",
              "question_text": "Django REST API를 설계할 때 본인이 직접 맡은 역할을 설명해주세요.",
              "question_type": "technical",
              "difficulty": null,
              "order_index": 1,
              "generation_reason": "JD의 Django API 요구사항 기반",
              "source_tags": [
                {
                  "source_type": "jd",
                  "source_label": "JD 기반",
                  "source_text_excerpt": "Django API 설계 경험"
                }
              ]
            }
          ]
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.generate_questions(self._question_generation_payload())
        question = result["questions"][0]

        self.assertFalse(result["fallback_used"])
        self.assertEqual(question["question_text"], "Django REST API를 설계할 때 본인이 직접 맡은 역할을 설명해주세요.")
        self.assertEqual(question["source_tags"][0]["source_type"], "jd")

    def test_openai_engine_raises_error_when_question_generation_returns_invalid_json(self):
        fake_client = FakeOpenAIClient("JSON이 아닌 응답")
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        with self.assertRaises(AIChainOpenAIError):
            engine.generate_questions(self._question_generation_payload())

    def test_openai_question_generation_preserves_expected_technical_keywords(self):
        raw_response = """{
          "session_id": "11111111-1111-1111-1111-111111111111",
          "questions": [
            {
              "client_question_key": "q_001",
              "question_text": "Explain the Django API transaction design.",
              "question_type": "main",
              "question_category": "technical",
              "expected_technical_keywords": [
                "Django transaction.atomic",
                "rollback",
                "idempotency"
              ],
              "difficulty": "medium",
              "order_index": 1,
              "source_tags": [{"source_type": "jd"}]
            }
          ]
        }"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.generate_questions(self._question_generation_payload())
        question = result["questions"][0]

        self.assertEqual(question["question_category"], "technical")
        self.assertEqual(
            question["expected_technical_keywords"],
            "Django transaction.atomic, rollback, idempotency",
        )

    def test_openai_engine_keeps_answer_sufficiency_contract_with_fallback(self):
        result = self.engine.judge_answer_sufficiency(self._sufficiency_payload())

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertTrue(result["should_generate_followup"])

    def test_openai_engine_uses_real_call_when_enabled_for_answer_sufficiency(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "is_sufficient": true,
          "sufficiency_reason": "충분한 답변입니다.",
          "answer_weakness_tags": [],
          "selected_weakness_tag": null,
          "should_generate_followup": false,
          "next_action": "NEXT_QUESTION"
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["answer"]["answer_text"] = (
            "I designed the Django API retry flow because OpenAI calls can fail "
            "transiently. I separated 502 retryable errors from validation errors, "
            "used transaction rollback to prevent failed rows, and verified the "
            "result with failure-rate metrics after deployment."
        )

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.NEXT_QUESTION.value)
        self.assertFalse(result["should_generate_followup"])
        self.assertTrue(result["is_sufficient"])

    def test_openai_engine_overrides_short_answer_next_question_to_followup(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "is_sufficient": true,
          "sufficiency_reason": "Model was too permissive.",
          "answer_weakness_tags": [],
          "selected_weakness_tag": null,
          "should_generate_followup": false,
          "next_action": "NEXT_QUESTION"
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["answer"]["answer_text"] = "I implemented the API."

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertTrue(result["should_generate_followup"])
        self.assertFalse(result["is_sufficient"])
        self.assertEqual(result["selected_weakness_tag"]["tag_name"], "TOO_SHORT")

    def test_openai_engine_overrides_abstract_answer_next_question_to_followup(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "is_sufficient": true,
          "sufficiency_reason": "Model was too permissive.",
          "answer_weakness_tags": [],
          "selected_weakness_tag": null,
          "should_generate_followup": false,
          "next_action": "NEXT_QUESTION"
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["answer"]["answer_text"] = (
            "I improved the Django API and made the backend service better for users."
        )

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertEqual(
            result["selected_weakness_tag"]["tag_name"],
            "ABSTRACT_ANSWER",
        )

    def test_openai_engine_accepts_sufficiency_decision_aliases(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "followup_decision": "follow_up",
          "trigger": "TECH_DEPTH_LOW",
          "sufficiency_reason": "Technical depth is too shallow."
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.judge_answer_sufficiency(self._sufficiency_payload())

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertTrue(result["should_generate_followup"])
        self.assertEqual(result["selected_weakness_tag"]["tag_name"], "TECH_DEPTH_LOW")

    def test_openai_engine_suppresses_overzealous_followup_for_sufficient_answer(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "is_sufficient": false,
          "sufficiency_reason": "Model was too aggressive.",
          "selected_weakness_tag": {
            "weakness_tag_id": "NO_ALTERNATIVE",
            "tag_name": "NO_ALTERNATIVE",
            "reason": "Needs more trade-off explanation."
          },
          "should_generate_followup": true,
          "next_action": "GENERATE_FOLLOWUP"
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["question"]["question_text"] = (
            "Explain how you optimized a Django API and why you chose that approach."
        )
        payload["answer"]["answer_text"] = (
            "In that project, I owned the backend API design and deployment. "
            "The initial problem was slow list responses caused by duplicate ORM "
            "queries and missing MySQL indexes. I analyzed the Django query plan, "
            "applied select_related and prefetch_related, and added an index for "
            "the main lookup condition. As a result, response time improved from "
            "about 1.8 seconds to 0.6 seconds. I also compared Redis caching, but "
            "because the data changed frequently, I chose query optimization first."
        )

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.NEXT_QUESTION.value)
        self.assertFalse(result["should_generate_followup"])
        self.assertTrue(result["is_sufficient"])
        self.assertIsNone(result["selected_weakness_tag"])

    def test_openai_engine_suppresses_overzealous_followup_for_korean_sufficient_answer(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "is_sufficient": false,
          "sufficiency_reason": "Model missed Korean sufficiency markers.",
          "selected_weakness_tag": {
            "weakness_tag_id": "NO_RESULT",
            "tag_name": "NO_RESULT",
            "reason": "Needs measurable outcome."
          },
          "should_generate_followup": true,
          "next_action": "GENERATE_FOLLOWUP"
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["question"]["question_text"] = (
            "해당 프로젝트에서 본인이 맡은 역할과 기술 선택 이유를 설명해 주세요."
        )
        payload["answer"]["answer_text"] = (
            "해당 프로젝트에서 저는 백엔드 API 설계와 배포를 담당했습니다. "
            "초기에는 응답 속도가 느린 문제가 있었고, 원인은 중복 쿼리와 인덱스 부재였습니다. "
            "저는 Django ORM 쿼리를 분석해서 select_related와 prefetch_related를 적용했고, "
            "조회 조건에 맞춰 MySQL 인덱스를 추가했습니다. "
            "그 결과 목록 조회 응답 시간이 약 1.8초에서 0.6초로 줄었습니다. "
            "Redis 캐싱도 검토했지만 데이터 갱신 빈도가 높아 우선 쿼리 최적화를 선택했습니다."
        )

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.NEXT_QUESTION.value)
        self.assertFalse(result["should_generate_followup"])
        self.assertTrue(result["is_sufficient"])
        self.assertIsNone(result["selected_weakness_tag"])

    def test_openai_engine_keeps_followup_for_korean_abstract_answer(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "is_sufficient": true,
          "sufficiency_reason": "Model was too permissive.",
          "answer_weakness_tags": [],
          "selected_weakness_tag": null,
          "should_generate_followup": false,
          "next_action": "NEXT_QUESTION"
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["question"]["question_text"] = (
            "해당 프로젝트에서 본인이 맡은 역할과 기술 선택 이유를 설명해 주세요."
        )
        payload["answer"]["answer_text"] = "프로젝트에서 백엔드를 열심히 했습니다."

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertTrue(result["should_generate_followup"])
        self.assertFalse(result["is_sufficient"])

    def test_openai_engine_keeps_high_severity_followup_for_korean_off_topic_answer(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "followup_decision": "GENERATE_FOLLOWUP",
          "trigger": "OFF_TOPIC",
          "sufficiency_reason": "The answer is long but unrelated to the technical question."
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["question"]["question_text"] = (
            "Django API 성능 문제를 어떻게 분석하고 해결했는지 설명해 주세요."
        )
        payload["answer"]["answer_text"] = (
            "동아리 행사에서 저는 홍보 문구 작성과 현장 안내를 담당했습니다. "
            "초기에는 참석자가 적은 문제가 있었고, 원인은 공지 시간이 늦었기 때문이었습니다. "
            "저는 안내 문구를 개선하고 채널별 발송 시간을 비교했습니다. "
            "그 결과 참석자가 늘었고, 다음 행사에서는 우선 홍보 일정을 앞당기는 방식을 선택했습니다."
        )

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertTrue(result["should_generate_followup"])
        self.assertEqual(result["selected_weakness_tag"]["tag_name"], "OFF_TOPIC")

    def test_openai_engine_keeps_high_severity_followup_for_off_topic_answer(self):
        raw_response = """```json
        {
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "follow_up_decision": "GENERATE_FOLLOWUP",
          "selected_trigger": "OFF_TOPIC",
          "sufficiency_reason": "The answer does not address the technical question."
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["question"]["question_text"] = (
            "Explain how you designed Django API error handling and database consistency."
        )
        payload["answer"]["answer_text"] = (
            "In a cooking contest, I organized ingredients, led the plating process, "
            "compared two garnish options, and won a small team award because the "
            "presentation looked cleaner. This gave me confidence in teamwork."
        )

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(result["next_action"], NextAction.GENERATE_FOLLOWUP.value)
        self.assertTrue(result["should_generate_followup"])
        self.assertEqual(result["selected_weakness_tag"]["tag_name"], "OFF_TOPIC")

    def test_openai_engine_raises_error_when_sufficiency_returns_invalid_json(self):
        fake_client = FakeOpenAIClient("JSON이 아닌 응답")
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        with self.assertRaises(AIChainOpenAIError):
            engine.judge_answer_sufficiency(self._sufficiency_payload())

    def test_openai_engine_uses_real_call_when_enabled_for_followup_generation(self):
        raw_response = """```json
        {
          "session_id": "11111111-1111-1111-1111-111111111111",
          "followup_question": {
            "parent_question_id": "22222222-2222-2222-2222-222222222222",
            "generated_from_answer_id": "33333333-3333-3333-3333-333333333333",
            "answer_weakness_tag_id": "44444444-4444-4444-4444-444444444444",
            "question_text": "방금 답변에서 본인이 직접 담당한 역할을 더 구체적으로 설명해주실 수 있나요?",
            "question_type": "technical",
            "difficulty": null,
            "order_index": 2,
            "generation_reason": "본인 기여도 불명확 태그 기준으로 생성"
          }
        }
        ```"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.generate_followup_question(self._followup_payload())
        followup = result["followup_question"]

        self.assertEqual(result["session_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(
            followup["question_text"],
            "방금 답변에서 본인이 직접 담당한 역할을 더 구체적으로 설명해주실 수 있나요?",
        )
        self.assertEqual(followup["parent_question_id"], "22222222-2222-2222-2222-222222222222")
        self.assertEqual(followup["generated_from_answer_id"], "33333333-3333-3333-3333-333333333333")
        self.assertEqual(followup["answer_weakness_tag_id"], "44444444-4444-4444-4444-444444444444")

    def test_openai_engine_raises_error_when_followup_returns_invalid_json(self):
        fake_client = FakeOpenAIClient("JSON이 아닌 응답")
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        with self.assertRaises(AIChainOpenAIError):
            engine.generate_followup_question(self._followup_payload())

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

    def test_request_text_calls_openai_client_and_returns_content(self):
        fake_client = FakeOpenAIClient('{"next_action": "NEXT_QUESTION"}')
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            model="gpt-test",
            client_factory=lambda api_key: fake_client,
        )

        result = engine._request_text(
            system_prompt="system prompt",
            user_prompt="user prompt",
            temperature=0.1,
            max_tokens=500,
        )

        self.assertEqual(result, '{"next_action": "NEXT_QUESTION"}')
        self.assertEqual(fake_client.completions.last_kwargs["model"], "gpt-test")
        self.assertEqual(fake_client.completions.last_kwargs["temperature"], 0.1)
        self.assertEqual(fake_client.completions.last_kwargs["max_tokens"], 500)
        self.assertEqual(
            fake_client.completions.last_kwargs["messages"][0]["content"],
            "system prompt",
        )
        self.assertEqual(
            fake_client.completions.last_kwargs["messages"][1]["content"],
            "user prompt",
        )

    @override_settings(OPENAI_API_KEY="")
    def test_get_client_raises_value_error_without_api_key(self):
        engine = AIChainOpenAIEngine(api_key="")

        with self.assertRaises(ValueError):
            engine._get_client()

    def test_parse_response_object_parses_markdown_fenced_json(self):
        raw_response = """```json
        {"next_action": "NEXT_QUESTION", "is_sufficient": true}
        ```"""

        result = self.engine._parse_response_object(raw_response)

        self.assertEqual(result["next_action"], "NEXT_QUESTION")
        self.assertTrue(result["is_sufficient"])

    def test_parse_response_object_returns_fallback_when_invalid(self):
        fallback = {
            "next_action": "NEXT_QUESTION",
            "is_sufficient": True,
        }

        result = self.engine._parse_response_object("JSON이 아닌 응답", fallback=fallback)

        self.assertEqual(result, fallback)

    def test_parse_response_list_parses_json_list(self):
        raw_response = """```json
        [{"tag_name": "답변 구체성 부족"}]
        ```"""

        result = self.engine._parse_response_list(raw_response)

        self.assertEqual(result[0]["tag_name"], "답변 구체성 부족")

    def test_parse_response_list_returns_fallback_when_invalid(self):
        fallback = [{"tag_name": "fallback"}]

        result = self.engine._parse_response_list("JSON이 아닌 응답", fallback=fallback)

        self.assertEqual(result, fallback)

    def test_openai_question_generation_normalizes_question_type_to_main(self):
        raw_response = '''```json
        {
          "session_id": "11111111-1111-1111-1111-111111111111",
          "questions": [
            {
              "client_question_key": "q_001",
              "question_text": "Django를 선택한 이유를 설명해주세요.",
              "question_type": "technical_choice",
              "difficulty": "medium",
              "order_index": 1,
              "generation_reason": "기술 선택 이유 확인",
              "source_tags": [
                {
                  "source_type": "job_description",
                  "source_label": "JD 기반",
                  "source_text_excerpt": "Django API 설계 경험"
                }
              ]
            }
          ]
        }
        ```'''
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.generate_questions(self._question_generation_payload())
        question = result["questions"][0]

        self.assertFalse(result["fallback_used"])
        self.assertEqual(question["question_type"], "main")
        self.assertEqual(question["source_tags"][0]["source_type"], "jd")

    def test_normalize_source_tags_maps_unknown_source_type_to_general(self):
        result = self.engine._normalize_source_tags(
            [
                {
                    "source_type": "unknown_source",
                    "source_label": "알 수 없는 출처",
                    "source_text_excerpt": "근거 문구",
                }
            ]
        )

        self.assertEqual(result[0]["source_type"], "general")
        self.assertEqual(result[0]["source_label"], "알 수 없는 출처")
        self.assertEqual(result[0]["source_text_excerpt"], "근거 문구")

    def test_normalize_source_tags_maps_source_type_aliases(self):
        result = self.engine._normalize_source_tags(
            [
                {
                    "source_type": "job_description",
                    "source_label": "JD 기반",
                    "source_text_excerpt": "Django API 설계 경험",
                },
                {
                    "source_type": "self_intro",
                    "source_label": "자기소개서 기반",
                    "source_text_excerpt": "프로젝트 경험",
                },
                {
                    "source_type": "project",
                    "source_label": "프로젝트 기반",
                    "source_text_excerpt": "AI 모의면접 시스템",
                },
            ]
        )

        self.assertEqual(result[0]["source_type"], "jd")
        self.assertEqual(result[1]["source_type"], "cover_letter")
        self.assertEqual(result[2]["source_type"], "project_experience")

    def _create_prompt_version(self, *, prompt_type, content, persona_type="practical"):
        persona, _ = PersonaConfig.objects.get_or_create(persona_type=persona_type)
        template = PromptTemplate.objects.create(
            persona_config=persona,
            title=f"{prompt_type} prompt",
            prompt_type=prompt_type,
        )
        version = PromptVersion.objects.create(
            template=template,
            version_number=1,
            content=content,
        )
        template.default_version = version
        template.save(update_fields=("default_version", "updated_at"))
        return version

    def test_question_generation_uses_db_prompt_and_returns_metadata(self):
        version = self._create_prompt_version(
            prompt_type="question_generation",
            content="DB QUESTION SYSTEM PROMPT",
        )
        raw_response = """{
          "session_id": "11111111-1111-1111-1111-111111111111",
          "questions": [
            {
              "question_text": "DB prompt question",
              "order_index": 1,
              "source_tags": [{"source_type": "general"}]
            }
          ]
        }"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.generate_questions(self._question_generation_payload())

        self.assertEqual(
            fake_client.completions.last_kwargs["messages"][0]["content"],
            "DB QUESTION SYSTEM PROMPT",
        )
        self.assertEqual(result["prompt_version_id"], version.id)
        self.assertEqual(result["prompt_source"], "db")

    def test_question_generation_uses_fallback_prompt_and_returns_metadata_without_db_prompt(self):
        raw_response = """{
          "session_id": "11111111-1111-1111-1111-111111111111",
          "questions": [
            {
              "question_text": "Fallback prompt question",
              "order_index": 1,
              "source_tags": [{"source_type": "general"}]
            }
          ]
        }"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.generate_questions(self._question_generation_payload())

        self.assertIn(
            "questions",
            fake_client.completions.last_kwargs["messages"][0]["content"],
        )
        self.assertIsNone(result["prompt_version_id"])
        self.assertEqual(result["prompt_source"], "fallback")

    def test_answer_sufficiency_uses_db_prompt_and_returns_metadata(self):
        version = self._create_prompt_version(
            prompt_type="answer_evaluation",
            content="DB ANSWER SYSTEM PROMPT",
        )
        raw_response = """{
          "answer_id": "33333333-3333-3333-3333-333333333333",
          "is_sufficient": true,
          "sufficiency_reason": "Enough detail.",
          "answer_weakness_tags": [],
          "selected_weakness_tag": null,
          "should_generate_followup": false,
          "next_action": "NEXT_QUESTION"
        }"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )
        payload = self._sufficiency_payload()
        payload["answer"]["answer_text"] = (
            "I designed the Django API retry flow because transient failures caused "
            "inconsistent results. I compared rollback and retry boundaries, added "
            "transaction handling, and confirmed the error rate dropped after release."
        )

        result = engine.judge_answer_sufficiency(payload)

        self.assertEqual(
            fake_client.completions.last_kwargs["messages"][0]["content"],
            "DB ANSWER SYSTEM PROMPT",
        )
        self.assertEqual(result["prompt_version_id"], version.id)
        self.assertEqual(result["prompt_source"], "db")

    def test_followup_generation_uses_db_prompt_and_returns_metadata(self):
        version = self._create_prompt_version(
            prompt_type="follow_up_generation",
            content="DB FOLLOWUP SYSTEM PROMPT",
        )
        raw_response = """{
          "session_id": "11111111-1111-1111-1111-111111111111",
          "followup_question": {
            "question_text": "DB prompt follow-up question",
            "order_index": 2
          }
        }"""
        fake_client = FakeOpenAIClient(raw_response)
        engine = AIChainOpenAIEngine(
            api_key="test-api-key",
            client_factory=lambda api_key: fake_client,
            enable_real_call=True,
        )

        result = engine.generate_followup_question(self._followup_payload())

        self.assertEqual(
            fake_client.completions.last_kwargs["messages"][0]["content"],
            "DB FOLLOWUP SYSTEM PROMPT",
        )
        self.assertEqual(result["prompt_version_id"], version.id)
        self.assertEqual(result["prompt_source"], "db")
