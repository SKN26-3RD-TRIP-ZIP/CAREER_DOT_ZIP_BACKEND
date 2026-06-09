"""
AI Chain OpenAI prompt templates.

배치 위치:
apps/interview/services/ai_chain_openai_prompts.py
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
        "당신은 IT 직무 모의면접 질문 생성 엔진입니다. "
        "반드시 JSON object만 반환하세요. "
        "최상위 필드는 session_id, questions를 포함해야 합니다. "
        "questions는 question_text, question_type, difficulty, order_index, "
        "generation_reason, source_tags를 포함한 객체 배열이어야 합니다. "
        "source_tags는 source_type, source_label, source_text_excerpt를 포함해야 합니다. "
        "질문은 사용자의 JD, 이력서, 자기소개서, 프로젝트 경험에 근거해야 합니다. "
        "질문 문체와 검증 강도는 위 면접관 페르소나 지시문을 따르세요."
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
        "당신은 IT 직무 모의면접 답변 평가 엔진입니다. "
        "반드시 JSON object만 반환하세요. "
        "필드는 answer_id, is_sufficient, sufficiency_reason, "
        "answer_weakness_tags, selected_weakness_tag, should_generate_followup, next_action을 포함해야 합니다. "
        "next_action은 NEXT_QUESTION 또는 GENERATE_FOLLOWUP 중 하나여야 합니다. "
        "답변 판단 기준과 추가 검증 강도는 위 면접관 페르소나 지시문을 따르세요."
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
    }
    return json.dumps(compact_payload, ensure_ascii=False)


def build_followup_system_prompt(persona: Any = None) -> str:
    persona_block = build_persona_prompt_block(persona)
    return (
        f"{persona_block}\n\n"
        "당신은 IT 직무 모의면접에서 지원자의 답변을 바탕으로 꼬리질문을 생성하는 면접관입니다. "
        "반드시 JSON object만 반환하세요. "
        "최상위 필드는 session_id, followup_question을 포함해야 합니다. "
        "followup_question은 parent_question_id, generated_from_answer_id, answer_weakness_tag_id, "
        "question_text, question_type, difficulty, order_index, generation_reason을 포함해야 합니다. "
        "question_text는 한 문장의 자연스러운 한국어 면접 질문이어야 합니다. "
        "꼬리질문의 말투와 압박 강도는 위 면접관 페르소나 지시문을 따르세요."
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
