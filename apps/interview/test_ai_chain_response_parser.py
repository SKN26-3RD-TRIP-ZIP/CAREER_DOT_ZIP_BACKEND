from django.test import SimpleTestCase

from apps.interview.services.ai_chain_response_parser import (
    extract_json_text,
    parse_llm_json,
    parse_llm_json_list,
    parse_llm_json_object,
    require_llm_json,
    strip_json_code_fence,
)


class AIChainResponseParserTest(SimpleTestCase):
    def test_strip_json_code_fence_returns_inner_json(self):
        raw = """```json
        {"next_action": "NEXT_QUESTION"}
        ```"""

        result = strip_json_code_fence(raw)

        self.assertEqual(result, '{"next_action": "NEXT_QUESTION"}')

    def test_parse_llm_json_parses_plain_json_object(self):
        raw = '{"next_action": "NEXT_QUESTION"}'

        result = parse_llm_json(raw)

        self.assertEqual(result["next_action"], "NEXT_QUESTION")

    def test_parse_llm_json_parses_markdown_fenced_json(self):
        raw = """```json
        {"next_action": "GENERATE_FOLLOWUP", "score": 0.4}
        ```"""

        result = parse_llm_json(raw)

        self.assertEqual(result["next_action"], "GENERATE_FOLLOWUP")
        self.assertEqual(result["score"], 0.4)

    def test_extract_json_text_extracts_json_from_mixed_response(self):
        raw = '분석 결과는 다음과 같습니다. {"is_sufficient": false, "reason": "부족"} 감사합니다.'

        result = extract_json_text(raw)

        self.assertEqual(result, '{"is_sufficient": false, "reason": "부족"}')

    def test_parse_llm_json_parses_json_list(self):
        raw = '[{"tag_name": "답변 구체성 부족"}]'

        result = parse_llm_json(raw)

        self.assertEqual(result[0]["tag_name"], "답변 구체성 부족")

    def test_parse_llm_json_returns_default_when_invalid(self):
        result = parse_llm_json("JSON이 아닌 응답입니다.", default={"fallback": True})

        self.assertEqual(result, {"fallback": True})

    def test_require_llm_json_raises_value_error_when_invalid(self):
        with self.assertRaises(ValueError):
            require_llm_json("JSON이 아닌 응답입니다.")

    def test_parse_llm_json_object_returns_default_when_result_is_not_object(self):
        result = parse_llm_json_object('[{"tag_name": "답변 구체성 부족"}]')

        self.assertEqual(result, {})

    def test_parse_llm_json_list_returns_default_when_result_is_not_list(self):
        result = parse_llm_json_list('{"next_action": "NEXT_QUESTION"}')

        self.assertEqual(result, [])
