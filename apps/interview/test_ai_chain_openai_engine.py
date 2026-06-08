from django.test import SimpleTestCase

from apps.interview.ai_chain_contracts import NextAction
from apps.interview.services.ai_chain_openai_engine import AIChainOpenAIEngine


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


class AIChainOpenAIEngineTest(SimpleTestCase):
    def setUp(self):
        self.engine = AIChainOpenAIEngine(api_key="test-api-key")

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
