from django.test import SimpleTestCase

from apps.interview.services.ai_chain_persona_prompts import (
    PERSONA_PROMPT_TEMPLATES,
    build_persona_instruction,
    build_persona_prompt_block,
    get_persona_label,
    get_persona_policy,
    normalize_persona_type,
)


class AIChainPersonaPromptsTest(SimpleTestCase):
    def test_persona_templates_have_three_official_types(self):
        self.assertEqual(
            set(PERSONA_PROMPT_TEMPLATES.keys()),
            {"coach", "practical", "verifier"},
        )

    def test_normalize_persona_type_returns_practical_by_default(self):
        self.assertEqual(normalize_persona_type(None), "practical")
        self.assertEqual(normalize_persona_type({}), "practical")
        self.assertEqual(normalize_persona_type("unknown"), "practical")

    def test_normalize_persona_type_supports_aliases(self):
        self.assertEqual(normalize_persona_type("kind"), "coach")
        self.assertEqual(normalize_persona_type("friendly"), "coach")
        self.assertEqual(normalize_persona_type("verify"), "verifier")
        self.assertEqual(normalize_persona_type("technical"), "verifier")
        self.assertEqual(normalize_persona_type("strict"), "verifier")

    def test_normalize_persona_type_reads_dict_persona_type(self):
        persona = {
            "persona_type": "friendly",
            "name": "친절한 코치형",
        }

        self.assertEqual(normalize_persona_type(persona), "coach")

    def test_build_persona_instruction_returns_different_tone_by_type(self):
        friendly = build_persona_instruction("coach")
        practical = build_persona_instruction("practical")
        verify = build_persona_instruction("verifier")

        self.assertIn("부드럽고 격려", friendly)
        self.assertIn("프로젝트 경험", practical)
        self.assertIn("근거 중심", verify)
        self.assertNotEqual(friendly, practical)
        self.assertNotEqual(practical, verify)

    def test_build_persona_prompt_block_contains_label_and_instruction(self):
        block = build_persona_prompt_block("verify")

        self.assertIn("persona_type: verifier", block)
        self.assertIn("검증 면접관형", block)
        self.assertIn("근거 중심", block)
        self.assertIn("verification_depth:", block)

    def test_persona_policy_is_structured_and_distinct(self):
        coach = get_persona_policy("friendly")
        practical = get_persona_policy("practical")
        verifier = get_persona_policy("verify")

        for policy in (coach, practical, verifier):
            self.assertIn("question_focus", policy)
            self.assertIn("followup_style", policy)
            self.assertIn("feedback_tone", policy)
            self.assertIn("verification_depth", policy)
            self.assertIn("forbidden_tone", policy)

        self.assertNotEqual(coach["followup_style"], practical["followup_style"])
        self.assertNotEqual(
            practical["verification_depth"],
            verifier["verification_depth"],
        )

    def test_get_persona_label_falls_back_to_practical(self):
        self.assertEqual(get_persona_label("unknown"), "실무 면접관형")
