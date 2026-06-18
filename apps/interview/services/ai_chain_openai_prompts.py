"""
AI Chain OpenAI prompt templates.
"""

from __future__ import annotations

import json
from typing import Any

from apps.interview.ai_chain_contracts import DEFAULT_WEAKNESS_TAG_CANDIDATES
from apps.interview.services.ai_chain_persona_prompts import build_persona_prompt_block


def build_question_generation_system_prompt(persona: Any = None) -> str:
    persona_block = build_persona_prompt_block(persona)
    return (
        f"{persona_block}\n\n"
        "You generate IT job interview questions. Return only a JSON object. "
        "The top-level fields must include session_id and questions. "
        "Each question must include question_text, question_type, question_category, "
        "difficulty, order_index, generation_reason, and source_tags. "
        "Set question_type to 'main' for all generated main questions. "
        "Set question_category to one of technical, personality, general. "
        "If generation_options.question_category_plan is provided, follow it in order. "
        "source_tags must include source_type, source_label, and source_text_excerpt. "
        "source_tags.source_type must be one of jd, resume, cover_letter, "
        "project_experience, or general. Prefer concrete input sources over general. "
        "Use general만 only when no concrete source applies."
    )


def build_question_generation_user_prompt(payload: dict[str, Any]) -> str:
    compact_payload = {
        "session_id": payload.get("session_id"),
        "persona": payload.get("persona"),
        "user_profile": payload.get("user_profile"),
        "input_sources": payload.get("input_sources"),
        "generation_options": payload.get("generation_options"),
    }
    return json.dumps(compact_payload, ensure_ascii=False)


def build_answer_sufficiency_system_prompt(persona: Any = None) -> str:
    persona_block = build_persona_prompt_block(persona)
    return (
        f"{persona_block}\n\n"
        "You evaluate whether an IT interview answer is sufficient. "
        "Return only a JSON object. Fields must include answer_id, is_sufficient, "
        "sufficiency_reason, answer_weakness_tags, selected_weakness_tag, "
        "should_generate_followup, and next_action. next_action must be either "
        "NEXT_QUESTION or GENERATE_FOLLOWUP."
    )


def build_answer_sufficiency_user_prompt(payload: dict[str, Any]) -> str:
    compact_payload = {
        "session_id": payload.get("session_id"),
        "question": payload.get("question"),
        "answer": payload.get("answer"),
        "persona": payload.get("persona"),
        "weakness_tag_candidates": (
            payload.get("weakness_tag_candidates") or DEFAULT_WEAKNESS_TAG_CANDIDATES
        ),
        "followup_decision_rules": {
            "generate_followup_when": [
                "TOO_SHORT",
                "ABSTRACT_ANSWER",
                "MISSING_REASON",
                "UNCLEAR_ROLE",
                "NO_RESULT",
                "TECH_DEPTH_LOW",
                "WEAK_JD_LINK",
                "STAR_MISSING",
                "NO_ALTERNATIVE",
                "OFF_TOPIC",
            ],
            "next_question_only_when": (
                "The answer has concrete situation, action, reason, "
                "personal contribution, and result."
            ),
            "selected_weakness_tag_tag_name_must_be_one_of_generate_followup_when": True,
        },
    }
    return json.dumps(compact_payload, ensure_ascii=False)


def build_followup_system_prompt(persona: Any = None) -> str:
    persona_block = build_persona_prompt_block(persona)
    return (
        f"{persona_block}\n\n"
        "You generate a follow-up question for an IT job interview. "
        "Return only a JSON object. The top-level fields must include session_id "
        "and followup_question. followup_question must include parent_question_id, "
        "generated_from_answer_id, answer_weakness_tag_id, question_text, "
        "question_type, difficulty, order_index, and generation_reason."
    )


def build_followup_user_prompt(payload: dict[str, Any]) -> str:
    compact_payload = {
        "session_id": payload.get("session_id"),
        "parent_question": payload.get("parent_question"),
        "answer": payload.get("answer"),
        "selected_weakness_tag": payload.get("selected_weakness_tag"),
        "persona": payload.get("persona"),
        "conversation_context": payload.get("conversation_context"),
    }
    return json.dumps(compact_payload, ensure_ascii=False)
