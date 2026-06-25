import re

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
    get_sufficiency_answer_text,
)


PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "forget previous instructions",
    "override your instructions",
    "reveal your prompt",
    "show your prompt",
    "print your prompt",
    "developer message",
    "이전 지시를 무시",
    "앞선 지시를 무시",
    "기존 지시를 무시",
    "명령을 무시",
    "프롬프트를 공개",
    "프롬프트를 보여",
    "프롬프트를 출력",
)

INTERNAL_CRITERIA_MARKERS = (
    "system prompt",
    "internal prompt",
    "hidden prompt",
    "evaluation rubric",
    "scoring rubric",
    "scoring formula",
    "score formula",
    "internal evaluation criteria",
    "시스템 프롬프트",
    "내부 프롬프트",
    "숨겨진 프롬프트",
    "내부 평가 기준",
    "평가 기준을 공개",
    "채점 기준을 공개",
    "점수 계산식",
    "채점 계산식",
)

OFF_TOPIC_TAGS = {
    "OFF_TOPIC",
    "WEAK_QUESTION_RELEVANCE",
    "QUESTION_RELEVANCE",
    "IRRELEVANT_ANSWER",
}

UNVERIFIED_CLAIM_TAGS = {
    "UNVERIFIED_CLAIM",
    "UNGROUNDED_CLAIM",
    "GROUNDING_REQUIRED",
    "SOURCE_VERIFICATION_REQUIRED",
}

OBVIOUS_OFF_TOPIC_MARKERS = (
    "오늘 점심",
    "점심 뭐",
    "뭐 먹지",
    "오늘 저녁",
    "저녁 뭐",
    "날씨가 좋",
    "날씨 좋",
    "상관없는 사담",
    "관련 없는 사담",
    "아무 상관없는",
    "what should i eat",
    "what's for lunch",
    "weather is nice",
    "nice weather",
    "unrelated small talk",
)

RELEVANCE_STOPWORDS = {
    "about",
    "answer",
    "describe",
    "explain",
    "how",
    "please",
    "question",
    "tell",
    "that",
    "the",
    "this",
    "what",
    "when",
    "where",
    "which",
    "why",
    "경험",
    "관련",
    "답변",
    "대해",
    "무엇",
    "설명",
    "어떻게",
    "어떤",
    "이유",
    "질문",
    "주세요",
}


def _normalize_guardrail_tag(value):
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _relevance_terms(text):
    return {
        token
        for token in re.findall(r"[a-z0-9가-힣]{2,}", str(text or "").lower())
        if token not in RELEVANCE_STOPWORDS
    }


def _is_obviously_off_topic(question_text, answer_text):
    """Conservatively detect explicit small talk unrelated to the question."""
    normalized_answer = str(answer_text or "").lower()
    if not any(marker in normalized_answer for marker in OBVIOUS_OFF_TOPIC_MARKERS):
        return False

    question_terms = _relevance_terms(question_text)
    answer_terms = _relevance_terms(answer_text)
    return not bool(question_terms & answer_terms)


def check_followup_guardrail(answer, selected_weakness_tag):
    """Decide whether follow-up generation may continue without side effects."""
    answer_text = str(get_sufficiency_answer_text(answer) or "").strip()
    question = getattr(answer, "question", None)
    question_text = str(getattr(question, "question_text", "") or "").strip()
    normalized_text = answer_text.lower()
    selected_tag_names = {
        _normalize_guardrail_tag(selected_weakness_tag.get(key))
        for key in ("tag_name", "weakness_tag_id", "code", "name")
        if isinstance(selected_weakness_tag, dict)
    }
    selected_tag_names.discard("")

    if selected_tag_names & OFF_TOPIC_TAGS:
        return {
            "can_generate_followup": False,
            "action": NextAction.NEXT_QUESTION.value,
            "reason": "off_topic_answer",
            "fallback_message": "질문과 관련된 경험이나 판단을 중심으로 답변해 주세요.",
        }

    if any(marker in normalized_text for marker in PROMPT_INJECTION_MARKERS):
        return {
            "can_generate_followup": False,
            "action": NextAction.NEXT_QUESTION.value,
            "reason": "prompt_injection_attempt",
            "fallback_message": "면접 질문에 대한 답변만 처리할 수 있습니다.",
        }

    if any(marker in normalized_text for marker in INTERNAL_CRITERIA_MARKERS):
        return {
            "can_generate_followup": False,
            "action": NextAction.NEXT_QUESTION.value,
            "reason": "internal_criteria_disclosure_request",
            "fallback_message": "내부 프롬프트나 평가 기준 대신 면접 답변을 이어가 주세요.",
        }

    if _is_obviously_off_topic(question_text, answer_text):
        return {
            "can_generate_followup": False,
            "action": NextAction.NEXT_QUESTION.value,
            "reason": "off_topic_answer",
            "fallback_message": "질문과 관련된 경험이나 판단을 중심으로 답변해 주세요.",
        }

    if selected_tag_names & UNVERIFIED_CLAIM_TAGS:
        return {
            "can_generate_followup": True,
            "action": "GENERATE_CONFIRMATION_FOLLOWUP",
            "reason": "claim_requires_verification",
            "fallback_message": "해당 주장을 확인할 수 있는 근거나 경험을 설명해 주세요.",
        }

    return {
        "can_generate_followup": True,
        "action": NextAction.GENERATE_FOLLOWUP.value,
        "reason": "allowed",
        "fallback_message": None,
    }


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

        guardrail_result = check_followup_guardrail(
            answer,
            selected_weakness_tag,
        )
        if not guardrail_result["can_generate_followup"]:
            cls._cache_no_followup_decision(answer, guardrail_result)
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
        # Deprecated candidate kept as a compatibility wrapper. New
        # integrations should use
        # InterviewAIChainService.evaluate_answer_sufficiency(answer). Keep
        # this method until all private-method consumers are migrated.
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
