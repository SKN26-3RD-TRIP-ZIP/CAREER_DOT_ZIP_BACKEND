from django.conf import settings
from django.db import transaction
from django.db.models import Max, Q

from apps.interview.ai_chain_contracts import (
    DEFAULT_WEAKNESS_TAG_CANDIDATES,
    NextAction,
)
from apps.interview.models import InterviewQuestion
from apps.interview.services.ai_chain_service import InterviewAIChainService


class FollowupGenerator:
    """답변 기반 꼬리질문 생성기.

    MVP 단계에서는 InterviewAIChainService의 mock 판단 로직을 사용한다.
    추후 LLM Chain으로 교체하더라도 create_followup(answer)의 외부 계약은 유지한다.
    """

    ai_chain_service = None

    @classmethod
    def create_followup(cls, answer):
        existing = (
            InterviewQuestion.objects.filter(
                Q(source_answer=answer) | Q(parent_question=answer.question),
                question_type="follow_up",
            )
            .order_by("order_index")
            .first()
        )
        if existing:
            return existing, False

        ai_chain_service = cls._get_ai_chain_service()

        sufficiency_payload = cls._build_sufficiency_payload(answer)
        sufficiency_result = ai_chain_service.judge_answer_sufficiency(
            sufficiency_payload
        )

        if sufficiency_result.get("next_action") == NextAction.NEXT_QUESTION.value:
            return None, False

        selected_weakness_tag = sufficiency_result.get("selected_weakness_tag")
        if not selected_weakness_tag:
            return None, False

        followup_payload = cls._build_followup_payload(
            answer=answer,
            selected_weakness_tag=selected_weakness_tag,
        )
        followup_result = ai_chain_service.generate_followup_question(
            followup_payload
        )
        followup_data = followup_result.get("followup_question")

        if not followup_data or not followup_data.get("question_text"):
            return None, False

        with transaction.atomic():
            last_index = (
                InterviewQuestion.objects.filter(session=answer.session)
                .aggregate(last=Max("order_index"))["last"]
                or 0
            )

            question = InterviewQuestion.objects.create(
                session=answer.session,
                parent_question=answer.question,
                source_answer=answer,
                question_text=followup_data["question_text"],
                question_type="follow_up",
                source_type="general",
                source_reference=cls._build_source_reference(
                    selected_weakness_tag,
                    followup_data,
                ),
                difficulty=followup_data.get("difficulty"),
                order_index=last_index + 1,
            )

        return question, True

    @classmethod
    def _build_sufficiency_payload(cls, answer):
        question = answer.question
        session = answer.session

        return {
            "session_id": str(session.id),
            "question": {
                "question_id": str(question.id),
                "question_text": question.question_text,
                "question_type": cls._map_question_type(question.question_type),
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
                "answer_text": answer.answer_text,
            },
            "persona": {
                "persona_id": None,
                "persona_type": cls._map_persona_type(session.persona),
                "name": session.persona,
                "description": "",
            },
            "prompt_version_id": None,
            "weakness_tag_candidates": DEFAULT_WEAKNESS_TAG_CANDIDATES,
        }

    @classmethod
    def _build_followup_payload(cls, answer, selected_weakness_tag):
        question = answer.question
        session = answer.session

        previous_followup_count = InterviewQuestion.objects.filter(
            session=session,
            parent_question=question,
            question_type="follow_up",
        ).count()

        previous_question_count = InterviewQuestion.objects.filter(
            session=session
        ).count()

        return {
            "session_id": str(session.id),
            "parent_question": {
                "question_id": str(question.id),
                "question_text": question.question_text,
                "question_type": cls._map_question_type(question.question_type),
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
                "answer_text": answer.answer_text,
            },
            "selected_weakness_tag": {
                "answer_weakness_tag_id": None,
                **selected_weakness_tag,
            },
            "persona": {
                "persona_id": None,
                "persona_type": cls._map_persona_type(session.persona),
                "name": session.persona,
                "description": "",
            },
            "prompt_version_id": None,
            "conversation_context": {
                "previous_question_count": previous_question_count,
                "previous_followup_count_for_parent": previous_followup_count,
            },
        }

    @staticmethod
    def _map_question_type(question_type):
        if question_type == "follow_up":
            return "job"
        if question_type == "main":
            return "job"
        return question_type or "job"

    @staticmethod
    def _map_persona_type(persona):
        if persona == "verifier":
            return "verify"
        if persona in {"coach", "practical", "verify"}:
            return persona
        return "practical"
    
    @classmethod
    def _get_ai_chain_service(cls):
        return cls.ai_chain_service or InterviewAIChainService()

    @staticmethod
    def _is_real_call_mode():
        return (
            str(getattr(settings, "INTERVIEW_AI_CHAIN_ENGINE", "mock")).lower()
            == "openai"
            and bool(getattr(settings, "INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL", False))
        )

    @classmethod
    def _build_source_reference(cls, selected_weakness_tag, followup_data=None):
        tag_name = selected_weakness_tag.get("tag_name") or "unknown"
        weakness_tag_id = (
            selected_weakness_tag.get("weakness_tag_id")
            or selected_weakness_tag.get("answer_weakness_tag_id")
            or "unknown"
        )
        prefix = "ai_chain" if cls._is_real_call_mode() else "ai_chain_mock"
        source_reference = f"{prefix}:{str(weakness_tag_id)[:36]}:{str(tag_name)[:40]}"

        if followup_data and cls._is_real_call_mode():
            reason = str(followup_data.get("generation_reason") or "").strip()
            if reason:
                source_reference = f"{source_reference}:{reason[:32]}"

        return source_reference[:100]


def generate_follow_up_questions(answer):
    followup, created = FollowupGenerator.create_followup(answer)
    if followup is None:
        return []
    return [
        {
            "question_type": followup.question_type,
            "question_text": followup.question_text,
            "source_type": followup.source_type,
            "source_reference": followup.source_reference,
        }
    ]
