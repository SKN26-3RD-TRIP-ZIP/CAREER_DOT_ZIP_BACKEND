from django.test import SimpleTestCase

from apps.interview.services.ai_chain_persona_prompts import (
    PERSONA_PROMPT_TEMPLATES,
    build_persona_instruction,
    build_persona_prompt_block,
    get_persona_label,
    normalize_persona_type,
)


class AIChainPersonaPromptsTest(SimpleTestCase):
    def test_persona_templates_have_three_official_types(self):
        self.assertEqual(
            set(PERSONA_PROMPT_TEMPLATES.keys()),
            {"friendly", "practical", "verify"},
        )

    def test_normalize_persona_type_returns_practical_by_default(self):
        self.assertEqual(normalize_persona_type(None), "practical")
        self.assertEqual(normalize_persona_type({}), "practical")
        self.assertEqual(normalize_persona_type("unknown"), "practical")

    def test_normalize_persona_type_supports_aliases(self):
        self.assertEqual(normalize_persona_type("kind"), "friendly")
        self.assertEqual(normalize_persona_type("coach"), "friendly")
        self.assertEqual(normalize_persona_type("verifier"), "verify")
        self.assertEqual(normalize_persona_type("technical"), "verify")
        self.assertEqual(normalize_persona_type("strict"), "verify")

    def test_normalize_persona_type_reads_dict_persona_type(self):
        persona = {
            "persona_type": "friendly",
            "name": "친절한 코치형",
        }

        self.assertEqual(normalize_persona_type(persona), "friendly")

    def test_build_persona_instruction_returns_different_tone_by_type(self):
        friendly = build_persona_instruction("friendly")
        practical = build_persona_instruction("practical")
        verify = build_persona_instruction("verify")

        self.assertIn("부드럽고 격려", friendly)
        self.assertIn("프로젝트 경험", practical)
        self.assertIn("근거 중심", verify)
        self.assertNotEqual(friendly, practical)
        self.assertNotEqual(practical, verify)

    def test_build_persona_prompt_block_contains_label_and_instruction(self):
        block = build_persona_prompt_block("verify")

        self.assertIn("persona_type: verify", block)
        self.assertIn("검증 면접관형", block)
        self.assertIn("근거 중심", block)

    def test_get_persona_label_falls_back_to_practical(self):
        self.assertEqual(get_persona_label("unknown"), "실무 면접관형")
