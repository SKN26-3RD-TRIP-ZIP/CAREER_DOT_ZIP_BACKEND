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
        "difficulty, order_index, generation_reason, source_tags, and "
        "expected_technical_keywords. "
        "Set question_type to 'main' for all generated main questions. "
        "Set question_category to one of technical, personality, general. "
        "For technical questions, set expected_technical_keywords to a concise "
        "comma-separated list of key technical concepts, not a model answer. "
        "For non-technical questions, use an empty string for expected_technical_keywords. "
        "If generation_options.question_category_plan is provided, follow it in order. "
        "When input_sources.project_experiences is present, generate project deep-dive "
        "questions around the candidate's role, contribution, implementation details, "
        "technology choices, alternatives and trade-offs, troubleshooting, and measurable "
        "outcomes. When input_sources.github_readme_context is present, use it as README "
        "context for project deep-dives: ask how README features were actually implemented, "
        "how architecture and technical challenges were handled, and what evidence supports "
        "the claimed results. Do not change the requested question_category_plan because of "
        "GitHub context; keep technical/personality/general categories as requested. "
        "When input_sources.job_description.effective_talent_profile is present, use it as "
        "JD talent-profile context. If effective_talent_profile.confirmed_by_user is true, "
        "treat its items as the user's confirmed interview-practice criteria and prioritize "
        "them over free-text job_description.talent_profile. Lower priority_order values "
        "are higher priority and should be reflected first when choosing talent-profile "
        "topics. Talent-profile questions must not be generic personality questions; they "
        "should verify whether the trait appears in the candidate's projects, experiences, "
        "technical choices, collaboration, troubleshooting, or trade-off decisions. If "
        "talent_profile_prompt_notice or effective_talent_profile.prompt_notice is present, "
        "follow it strictly. Do not claim these traits are official company values unless "
        "the payload explicitly supports that; they may be user-confirmed or user-entered "
        "criteria for interview practice. "
        "source_tags must include source_type, source_label, and source_text_excerpt. "
        "source_tags.source_type must be one of jd, resume, cover_letter, "
        "project_experience, or general. Prefer concrete input sources over general. "
        "For README-based project questions, include a source tag with "
        "source_type='project_experience' and source_label='github_readme_context'. "
        "For talent-profile-based questions, include a source tag with source_type='jd' "
        "and source_label='effective_talent_profile' or source_label='talent_profile'. "
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
        "interview_type": payload.get("interview_type"),
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
        "question_type, difficulty, order_index, and generation_reason. "
        "Use parent_question.question_category and followup_context.category_guidance "
        "as hard constraints for the angle of the follow-up. "
        "If question_category is personality, do not turn the answer into a technical "
        "knowledge check even when the answer mentions tools such as Docker, Kubernetes, "
        "Redis, or APIs. Focus on decision process, collaboration, communication, "
        "problem solving, conflict resolution, reflection, ownership, or stakeholder "
        "alignment. Prefer questions like 'How did you share and align that choice with "
        "your team?' over 'Why did you use Docker itself?'. "
        "If question_category is technical, focus on implementation principles, "
        "technology choice rationale, troubleshooting, alternatives, trade-offs, "
        "failure modes, and job-relevant technical depth. "
        "For every follow-up, do not assert unsupported external facts or market claims. "
        "Do not claim that a technology is rarely used in real work, meaningless in the "
        "field, obsolete, or not used in practice unless that fact is explicitly provided "
        "in the payload. Avoid unsupported premises such as 'this is not used in the "
        "industry' or 'it has no practical value'. When challenging a choice, ask "
        "neutrally, for example: 'What evidence made that choice appropriate for the "
        "situation?'"
    )


def build_followup_user_prompt(payload: dict[str, Any]) -> str:
    compact_payload = {
        "session_id": payload.get("session_id"),
        "interview_type": payload.get("interview_type"),
        "parent_question": payload.get("parent_question"),
        "answer": payload.get("answer"),
        "selected_weakness_tag": payload.get("selected_weakness_tag"),
        "persona": payload.get("persona"),
        "followup_context": payload.get("followup_context"),
        "conversation_context": payload.get("conversation_context"),
    }
    return json.dumps(compact_payload, ensure_ascii=False)
