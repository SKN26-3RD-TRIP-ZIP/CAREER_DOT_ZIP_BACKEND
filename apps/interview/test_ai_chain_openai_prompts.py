import json

from django.test import SimpleTestCase

from apps.interview.services.ai_chain_openai_prompts import (
    build_answer_sufficiency_system_prompt,
    build_answer_sufficiency_user_prompt,
    build_followup_system_prompt,
    build_followup_user_prompt,
    build_question_generation_system_prompt,
    build_question_generation_user_prompt,
)


class AIChainOpenAIPromptsTest(SimpleTestCase):
    def test_question_generation_system_prompt_includes_persona_instruction(self):
        prompt = build_question_generation_system_prompt({"persona_type": "friendly"})

        self.assertIn("persona_type: coach", prompt)
        self.assertIn("친절한 코치형", prompt)
        self.assertIn("session_id", prompt)
        self.assertIn("questions", prompt)
        self.assertIn("source_tags", prompt)
        self.assertIn("expected_technical_keywords", prompt)

    def test_question_generation_user_prompt_serializes_payload(self):
        payload = {
            "session_id": "session-1",
            "persona": {"persona_type": "practical"},
            "user_profile": {"career_type": "신입"},
            "input_sources": {"job_description": {"position": "Backend Developer"}},
            "generation_options": {"question_count": 3},
        }

        result = json.loads(build_question_generation_user_prompt(payload))

        self.assertEqual(result["session_id"], "session-1")
        self.assertEqual(result["generation_options"]["question_count"], 3)

    def test_answer_sufficiency_system_prompt_includes_persona_instruction(self):
        prompt = build_answer_sufficiency_system_prompt({"persona_type": "verify"})

        self.assertIn("persona_type: verifier", prompt)
        self.assertIn("검증 면접관형", prompt)
        self.assertIn("next_action", prompt)
        self.assertIn("NEXT_QUESTION", prompt)
        self.assertIn("GENERATE_FOLLOWUP", prompt)

    def test_answer_sufficiency_user_prompt_includes_default_weakness_candidates(self):
        payload = {
            "session_id": "session-1",
            "question": {"question_text": "질문"},
            "answer": {"answer_text": "답변"},
            "persona": {"persona_type": "practical"},
        }

        result = json.loads(build_answer_sufficiency_user_prompt(payload))

        self.assertIn("weakness_tag_candidates", result)
        self.assertGreaterEqual(len(result["weakness_tag_candidates"]), 1)

    def test_followup_system_prompt_includes_persona_instruction(self):
        prompt = build_followup_system_prompt({"persona_type": "practical"})

        self.assertIn("persona_type: practical", prompt)
        self.assertIn("실무 면접관형", prompt)
        self.assertIn("followup_question", prompt)
        self.assertIn("question_text", prompt)

    def test_followup_user_prompt_serializes_payload(self):
        payload = {
            "session_id": "session-1",
            "parent_question": {"question_text": "원 질문"},
            "answer": {"answer_text": "답변"},
            "selected_weakness_tag": {"tag_name": "답변 구체성 부족"},
            "persona": {"persona_type": "practical"},
            "conversation_context": {"previous_question_count": 1},
        }

        result = json.loads(build_followup_user_prompt(payload))

        self.assertEqual(result["session_id"], "session-1")
        self.assertEqual(result["selected_weakness_tag"]["tag_name"], "답변 구체성 부족")

    def test_question_generation_system_prompt_guides_main_question_type_and_source_tags(self):
        prompt = build_question_generation_system_prompt()

        self.assertIn("main", prompt)
        self.assertIn("jd", prompt)
        self.assertIn("resume", prompt)
        self.assertIn("cover_letter", prompt)
        self.assertIn("project_experience", prompt)
        self.assertIn("general", prompt)
        self.assertIn("general만", prompt)

    def test_question_generation_system_prompt_guides_talent_profile_usage(self):
        prompt = build_question_generation_system_prompt()

        self.assertIn("effective_talent_profile", prompt)
        self.assertIn("confirmed_by_user", prompt)
        self.assertIn("priority_order", prompt)
        self.assertIn("talent_profile_prompt_notice", prompt)
        self.assertIn("source_label='effective_talent_profile'", prompt)
        self.assertIn("source_label='talent_profile'", prompt)
