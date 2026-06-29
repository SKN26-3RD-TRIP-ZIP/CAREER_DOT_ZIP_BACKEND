from apps.interview.ai_chain_contracts import DEFAULT_WEAKNESS_TAG_CANDIDATES
from apps.interview.services.ai_chain_persona_prompts import (
    get_persona_policy,
    normalize_persona_type,
)
from apps.interview.services.guardrails import mask_text_for_llm


EXPECTED_TECHNICAL_KEYWORDS_LABEL = "expected_technical_keywords"


def get_sufficiency_answer_text(answer):
    if answer.session.interview_mode == "voice" and answer.stt_text:
        return mask_text_for_llm(answer.stt_text)
    return mask_text_for_llm(answer.answer_text)


def get_question_category(question):
    category = str(getattr(question, "question_category", "") or "").strip().lower()
    if category in {"technical", "personality", "general"}:
        return category
    return "general"


def get_expected_technical_keywords(question):
    if get_question_category(question) != "technical":
        return ""

    keyword_tag = (
        question.source_tags.filter(
            source_label=EXPECTED_TECHNICAL_KEYWORDS_LABEL,
        )
        .order_by("id")
        .first()
    )
    if keyword_tag is None:
        return ""
    return str(keyword_tag.source_text_excerpt or "").strip()


def build_question_context(question, session):
    return {
        "question_category": get_question_category(question),
        "interview_type": session.interview_type,
        "expected_technical_keywords": get_expected_technical_keywords(question),
    }


def build_sufficiency_payload_from_answer(answer):
    question = answer.question
    session = answer.session
    question_context = build_question_context(question, session)

    return {
        "session_id": str(session.id),
        "interview_type": session.interview_type,
        "question": {
            "question_id": str(question.id),
            "question_text": question.question_text,
            "question_type": _map_question_type(question.question_type),
            **question_context,
            "parent_question_id": (
                str(question.parent_question_id)
                if question.parent_question_id
                else None
            ),
            "source_tags": [
                {
                    "source_type": question.source_type or "general",
                    "source_label": question.source_type or "general",
                    "source_text_excerpt": question.source_reference or "",
                }
            ],
        },
        "answer": {
            "answer_id": str(answer.id),
            "answer_text": get_sufficiency_answer_text(answer),
        },
        "persona": {
            "persona_id": None,
            "persona_type": _map_persona_type(session.persona),
            "name": session.persona,
            "description": "",
            "policy": get_persona_policy(session.persona),
        },
        "prompt_version_id": None,
        "weakness_tag_candidates": DEFAULT_WEAKNESS_TAG_CANDIDATES,
    }


def _map_question_type(question_type):
    if question_type in {"main", "follow_up"}:
        return "job"
    return question_type or "job"


def _map_persona_type(persona):
    return normalize_persona_type(persona)
