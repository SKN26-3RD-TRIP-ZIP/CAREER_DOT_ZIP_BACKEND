from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max, Q

from apps.evaluation.models import AnswerWeaknessTag, WeaknessTag
from apps.interview.ai_chain_contracts import (
    NextAction,
)
from apps.interview.models import InterviewQuestion
from apps.interview.services.ai_chain_service import InterviewAIChainService
from apps.interview.services.sufficiency_payload import (
    build_sufficiency_payload_from_answer,
)


class FollowupGenerator:
    """답변 기반 꼬리질문 생성기.

    MVP 단계에서는 InterviewAIChainService의 mock 판단 로직을 사용한다.
    추후 LLM Chain으로 교체하더라도 create_followup(answer)의 외부 계약은 유지한다.
    """

    ai_chain_service = None
    sufficiency_cache_timeout_seconds = 60 * 60 * 24

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

        if cls._has_cached_no_followup_decision(answer):
            return None, False

        ai_chain_service = cls._get_ai_chain_service()

        sufficiency_payload = cls._build_sufficiency_payload(answer)
        sufficiency_result = ai_chain_service.judge_answer_sufficiency(
            sufficiency_payload
        )

        if not cls._should_generate_followup(sufficiency_result):
            cls._cache_no_followup_decision(answer, sufficiency_result)
            return None, False

        selected_weakness_tag = sufficiency_result.get("selected_weakness_tag")
        if not selected_weakness_tag:
            return None, False

        answer_weakness_mapping = cls._get_or_create_answer_weakness_mapping(
            answer,
            selected_weakness_tag,
        )
        selected_weakness_tag = {
            **selected_weakness_tag,
            "answer_weakness_tag_id": str(answer_weakness_mapping.id),
            "weakness_tag_id": str(answer_weakness_mapping.weakness_tag_id),
            "tag_name": answer_weakness_mapping.weakness_tag.tag_name,
        }

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
            cls._link_weakness_mapping_to_followup(
                answer_weakness_mapping,
                question,
            )

        return question, True

    @classmethod
    def _build_sufficiency_payload(cls, answer):
        return build_sufficiency_payload_from_answer(answer)

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
    def _get_or_create_answer_weakness_mapping(cls, answer, selected_weakness_tag):
        tag_name = cls._normalize_weakness_tag_name(
            selected_weakness_tag.get("tag_name")
            or selected_weakness_tag.get("weakness_tag_id")
            or selected_weakness_tag.get("code")
            or selected_weakness_tag.get("name")
        )
        reason = (
            selected_weakness_tag.get("reason")
            or selected_weakness_tag.get("description")
            or ""
        )

        weakness_tag, created = WeaknessTag.objects.get_or_create(
            tag_name=tag_name,
            defaults={"description": reason},
        )
        if not created and reason and not weakness_tag.description:
            weakness_tag.description = reason
            weakness_tag.save(update_fields=("description",))

        mapping = AnswerWeaknessTag.objects.filter(
            answer=answer,
            weakness_tag=weakness_tag,
        ).first()
        if mapping is None:
            next_rank = (
                AnswerWeaknessTag.objects.filter(answer=answer)
                .aggregate(last=Max("priority_rank"))["last"]
                or 0
            ) + 1
            mapping = AnswerWeaknessTag.objects.create(
                answer=answer,
                weakness_tag=weakness_tag,
                reason=reason,
                priority_rank=next_rank,
                is_selected_for_followup=True,
                used_for="followup",
            )
            return mapping

        update_fields = []
        if reason and not mapping.reason:
            mapping.reason = reason
            update_fields.append("reason")
        if not mapping.is_selected_for_followup:
            mapping.is_selected_for_followup = True
            update_fields.append("is_selected_for_followup")
        if not mapping.used_for:
            mapping.used_for = "followup"
            update_fields.append("used_for")
        if update_fields:
            mapping.save(update_fields=tuple(update_fields))
        return mapping

    @staticmethod
    def _normalize_weakness_tag_name(raw_tag_name):
        tag_name = str(raw_tag_name or "ABSTRACT_ANSWER").strip()
        normalized = tag_name.upper().replace("-", "_").replace(" ", "_")
        trigger_aliases = {
            "TOO_SHORT": "weak_specificity",
            "ABSTRACT_ANSWER": "weak_specificity",
            "MISSING_REASON": "weak_technical_reasoning",
            "UNCLEAR_ROLE": "weak_personal_contribution",
            "NO_RESULT": "weak_result_impact",
            "TECH_DEPTH_LOW": "weak_technical_understanding",
            "WEAK_JD_LINK": "weak_jd_fit",
            "STAR_MISSING": "weak_answer_structure",
            "NO_ALTERNATIVE": "weak_technical_reasoning",
            "OFF_TOPIC": "weak_question_relevance",
        }
        return trigger_aliases.get(normalized, tag_name)

    @staticmethod
    def _link_weakness_mapping_to_followup(mapping, question):
        update_fields = []
        if mapping.followup_question_id != question.id:
            mapping.followup_question_id = question.id
            update_fields.append("followup_question_id")
        if mapping.used_for != "followup":
            mapping.used_for = "followup"
            update_fields.append("used_for")
        if not mapping.is_selected_for_followup:
            mapping.is_selected_for_followup = True
            update_fields.append("is_selected_for_followup")
        if update_fields:
            mapping.save(update_fields=tuple(update_fields))
    
    @classmethod
    def _get_ai_chain_service(cls):
        return cls.ai_chain_service or InterviewAIChainService()

    @staticmethod
    def _should_generate_followup(sufficiency_result):
        next_action = sufficiency_result.get("next_action")
        if next_action == NextAction.GENERATE_FOLLOWUP.value:
            return True
        if next_action == NextAction.NEXT_QUESTION.value:
            return False

        should_generate_followup = sufficiency_result.get("should_generate_followup")
        if isinstance(should_generate_followup, bool):
            return should_generate_followup

        return False

    @classmethod
    def _has_cached_no_followup_decision(cls, answer):
        return cache.get(cls._no_followup_cache_key(answer)) is True

    @classmethod
    def _cache_no_followup_decision(cls, answer, sufficiency_result):
        cache.set(
            cls._no_followup_cache_key(answer),
            True,
            timeout=cls.sufficiency_cache_timeout_seconds,
        )

    @staticmethod
    def _no_followup_cache_key(answer):
        return f"interview:no_followup:{answer.id}:{answer.updated_at.timestamp()}"

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
            selected_weakness_tag.get("answer_weakness_tag_id")
            or selected_weakness_tag.get("weakness_tag_id")
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
