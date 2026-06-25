from apps.interview.ai_chain_contracts import DEFAULT_WEAKNESS_TAG_CANDIDATES


def get_sufficiency_answer_text(answer):
    if answer.session.interview_mode == "voice" and answer.stt_text:
        return answer.stt_text
    return answer.answer_text


def build_sufficiency_payload_from_answer(answer):
    question = answer.question
    session = answer.session

    return {
        "session_id": str(session.id),
        "question": {
            "question_id": str(question.id),
            "question_text": question.question_text,
            "question_type": _map_question_type(question.question_type),
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
        },
        "prompt_version_id": None,
        "weakness_tag_candidates": DEFAULT_WEAKNESS_TAG_CANDIDATES,
    }


def _map_question_type(question_type):
    if question_type in {"main", "follow_up"}:
        return "job"
    return question_type or "job"


def _map_persona_type(persona):
    if persona == "verifier":
        return "verify"
    if persona in {"coach", "practical", "verify"}:
        return persona
    return "practical"
