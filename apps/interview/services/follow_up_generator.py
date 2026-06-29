import json
import re

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max, Q

from apps.evaluation.models import AnswerWeaknessTag, WeaknessTag
from apps.input.services.talent_profile_service import resolve_effective_talent_profile
from apps.interview.ai_chain_contracts import (
    NextAction,
)
from apps.interview.models import InterviewQuestion, QuestionSourceTag
from apps.interview.services.ai_chain_service import InterviewAIChainService
from apps.interview.services.ai_chain_persona_prompts import (
    get_persona_policy,
    normalize_persona_type,
)
from apps.interview.services.sufficiency_payload import (
    build_question_context,
    build_sufficiency_payload_from_answer,
    get_question_category,
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

DOCUMENT_CLAIM_KEYWORDS = {
    "airflow",
    "ansible",
    "aws",
    "azure",
    "cassandra",
    "databricks",
    "docker",
    "dynamodb",
    "elasticsearch",
    "firebase",
    "flink",
    "gcp",
    "graphql",
    "hadoop",
    "istio",
    "kafka",
    "kubernetes",
    "mongodb",
    "nasa",
    "neo4j",
    "oracle",
    "pytorch",
    "rabbitmq",
    "redis",
    "snowflake",
    "spark",
    "terraform",
    "tensorflow",
}

DOCUMENT_CLAIM_ALIASES = {
    "k8s": "kubernetes",
    "쿠버네티스": "kubernetes",
    "그래프ql": "graphql",
    "그래프큐엘": "graphql",
    "도커": "docker",
    "테라폼": "terraform",
    "카프카": "kafka",
    "레디스": "redis",
}

EXPERIENCE_CLAIM_MARKERS = (
    "i built",
    "i developed",
    "i implemented",
    "i led",
    "i migrated",
    "i operated",
    "i worked",
    "my project",
    "my role",
    "경험이 있습니다",
    "구축했습니다",
    "개발했습니다",
    "구현했습니다",
    "담당했습니다",
    "도입했습니다",
    "마이그레이션했습니다",
    "운영했습니다",
    "참여했습니다",
    "프로젝트에서",
    "사용했습니다",
    "수행했습니다",
    "재직했습니다",
)

MAX_FOLLOWUPS_PER_MAIN_QUESTION = 1
MAX_FOLLOWUPS_PER_SESSION = 2

CONFIRMATION_FOLLOWUP_MESSAGE = (
    "제출하신 문서에서는 해당 경험이 확인되지 않아요. "
    "이 경험이 실제 본인 프로젝트라면 수행 기간과 본인 역할을 간단히 설명해 주세요."
)

CONFIRMATION_FOLLOWUP_MESSAGES = {
    "coach": (
        "제출하신 문서에서는 해당 경험이 확인되지 않아요. "
        "이 경험을 더 잘 이해할 수 있도록 수행한 시기와 본인이 맡은 역할부터 편하게 설명해 주세요."
    ),
    "practical": (
        "제출하신 문서에서는 해당 경험이 확인되지 않아요. "
        "실제 수행 경험이라면 수행 기간과 본인 역할, 직접 구현한 내용을 구체적으로 설명해 주세요."
    ),
    "verifier": (
        "제출하신 문서에서는 해당 경험이 확인되지 않습니다. "
        "사실 관계를 확인할 수 있도록 수행 기간, 본인 기여도와 이를 뒷받침하는 구체적 근거를 설명해 주세요."
    ),
}


def get_confirmation_followup_message(persona):
    persona_type = normalize_persona_type(persona)
    return CONFIRMATION_FOLLOWUP_MESSAGES.get(
        persona_type,
        CONFIRMATION_FOLLOWUP_MESSAGE,
    )


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


def _stringify_context_value(value):
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _build_document_context(answer):
    session = answer.session
    question = answer.question
    context_parts = [question.question_text, question.source_reference]

    for source_tag in question.source_tags.all():
        context_parts.extend(
            (
                source_tag.source_label,
                source_tag.source_text_excerpt,
                source_tag.source_reference,
            )
        )

    jd = session.jd
    if jd is not None:
        effective_talent_profile = resolve_effective_talent_profile(jd)
        context_parts.extend(
            (
                jd.company_name,
                jd.position,
                jd.original_text,
                jd.company_summary,
                jd.talent_profile,
                effective_talent_profile.get("summary"),
                effective_talent_profile.get("prompt_notice"),
                effective_talent_profile.get("items"),
                jd.job_requirements,
                jd.keywords,
            )
        )

    resume = session.resume
    if resume is not None:
        context_parts.extend((resume.original_text, resume.extracted_keywords))
        context_parts.extend(resume.skills.values_list("name", flat=True))
        for career in resume.careers.all():
            context_parts.extend(
                (
                    career.company_name,
                    career.position,
                    career.description,
                )
            )

    cover_letter = session.cover_letter
    if cover_letter is not None:
        context_parts.extend((cover_letter.title, cover_letter.company_name))
        for item in cover_letter.items.all():
            context_parts.extend((item.question, item.answer_text))

    try:
        from apps.analysis.models import JdAnalysis

        analysis = (
            JdAnalysis.objects.filter(
                user_id=session.user_id,
                jd_id=session.jd_id,
                resume_id=session.resume_id,
            )
            .order_by("-analyzed_at")
            .first()
        )
        if analysis is not None:
            context_parts.extend(
                (
                    analysis.matched_keywords,
                    analysis.unmatched_keywords,
                    analysis.jd_keywords,
                    analysis.resume_analysis,
                    analysis.strengths,
                    analysis.weaknesses,
                    analysis.cl_points,
                )
            )
    except Exception:
        # Document guardrail must degrade safely when optional analysis data
        # is unavailable; the original follow-up flow should remain usable.
        pass

    return " ".join(_stringify_context_value(value) for value in context_parts)


def _extract_claim_keywords(text):
    normalized_text = str(text or "").lower()
    keywords = {
        keyword
        for keyword in DOCUMENT_CLAIM_KEYWORDS
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", normalized_text)
    }
    for alias, canonical in DOCUMENT_CLAIM_ALIASES.items():
        if alias in normalized_text:
            keywords.add(canonical)
    return keywords


def _find_unverified_document_claim(answer, answer_text):
    normalized_answer = str(answer_text or "").lower()
    if not any(marker in normalized_answer for marker in EXPERIENCE_CLAIM_MARKERS):
        return set()

    answer_keywords = _extract_claim_keywords(answer_text)
    if not answer_keywords:
        return set()

    context_keywords = _extract_claim_keywords(_build_document_context(answer))
    return answer_keywords - context_keywords


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

    unverified_keywords = _find_unverified_document_claim(answer, answer_text)
    if unverified_keywords:
        return {
            "can_generate_followup": True,
            "action": "GENERATE_CONFIRMATION_FOLLOWUP",
            "reason": "claim_requires_document_confirmation",
            "fallback_message": get_confirmation_followup_message(
                answer.session.persona
            ),
            "unverified_keywords": sorted(unverified_keywords),
        }

    if selected_tag_names & UNVERIFIED_CLAIM_TAGS:
        return {
            "can_generate_followup": True,
            "action": "GENERATE_CONFIRMATION_FOLLOWUP",
            "reason": "claim_requires_verification",
            "fallback_message": get_confirmation_followup_message(
                answer.session.persona
            ),
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
        main_question = cls._get_main_question(answer.question)
        existing_filter = Q(source_answer=answer)
        if answer.question.question_type == "main":
            existing_filter |= Q(parent_question=main_question)
        existing = (
            InterviewQuestion.objects.filter(existing_filter, question_type="follow_up")
            .order_by("order_index")
            .first()
        )
        if existing:
            return existing, False

        if cls._has_cached_no_followup_decision(answer):
            return None, False

        limit_decision = cls._check_followup_limit(answer)
        if not limit_decision["can_generate_followup"]:
            cls._cache_no_followup_decision(answer, limit_decision)
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

        if guardrail_result["action"] == "GENERATE_CONFIRMATION_FOLLOWUP":
            return cls._create_confirmation_followup(
                answer,
                guardrail_result,
            )

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
                question_category=get_question_category(answer.question),
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
            cls._save_generation_metadata_tags(
                question,
                followup_result,
                answer.session.persona,
            )

        return question, True

    @classmethod
    def _create_confirmation_followup(cls, answer, guardrail_result):
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
                question_text=(
                    guardrail_result.get("fallback_message")
                    or CONFIRMATION_FOLLOWUP_MESSAGE
                ),
                question_type="follow_up",
                question_category=get_question_category(answer.question),
                source_type="general",
                source_reference="guardrail:document_confirmation",
                difficulty="medium",
                order_index=last_index + 1,
            )
            cls._save_generation_metadata_tags(
                question,
                {
                    "generation_source": "guardrail",
                    "prompt_type": "follow_up_generation",
                    "prompt_source": "not_used",
                    "reason": guardrail_result.get("reason"),
                },
                answer.session.persona,
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
    def _check_followup_limit(cls, answer):
        session = answer.session
        main_question = cls._get_main_question(answer.question)
        max_per_main = cls._get_max_followups_per_main_question(session)
        max_per_session = cls._get_max_followups_per_session(session)

        main_followup_count = InterviewQuestion.objects.filter(
            session=session,
            parent_question=main_question,
            question_type="follow_up",
        ).count()
        if main_followup_count >= max_per_main:
            return cls._limit_decision("max_followups_per_main_question_reached")

        session_followup_count = InterviewQuestion.objects.filter(
            session=session,
            question_type="follow_up",
        ).count()
        if session_followup_count >= max_per_session:
            return cls._limit_decision("max_followups_per_session_reached")

        hard_limit = cls._get_session_question_hard_limit(session)
        session_question_count = InterviewQuestion.objects.filter(
            session=session,
        ).count()
        if session_question_count >= hard_limit:
            return cls._limit_decision("session_question_hard_limit_reached")

        return {
            "can_generate_followup": True,
            "action": NextAction.GENERATE_FOLLOWUP.value,
            "reason": "allowed",
            "fallback_message": None,
        }

    @staticmethod
    def _get_main_question(question):
        current = question
        visited = set()
        while (
            current is not None
            and current.question_type == "follow_up"
            and current.parent_question_id
            and current.id not in visited
        ):
            visited.add(current.id)
            current = current.parent_question
        return current or question

    @staticmethod
    def _get_max_followups_per_main_question(_session):
        return MAX_FOLLOWUPS_PER_MAIN_QUESTION

    @staticmethod
    def _get_max_followups_per_session(_session):
        return MAX_FOLLOWUPS_PER_SESSION

    @classmethod
    def _get_session_question_hard_limit(cls, session):
        main_question_count = InterviewQuestion.objects.filter(
            session=session,
            question_type="main",
        ).count()
        if main_question_count <= 0:
            main_question_count = int(session.total_question_count or 0)
        return main_question_count + cls._get_max_followups_per_session(session)

    @staticmethod
    def _limit_decision(reason):
        return {
            "can_generate_followup": False,
            "action": NextAction.NEXT_QUESTION.value,
            "reason": reason,
            "fallback_message": "꼬리질문 제한에 도달해 다음 질문으로 진행합니다.",
        }

    @classmethod
    def _build_followup_payload(cls, answer, selected_weakness_tag):
        question = answer.question
        session = answer.session
        question_context = build_question_context(question, session)

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
            "interview_type": session.interview_type,
            "parent_question": {
                "question_id": str(question.id),
                "question_text": question.question_text,
                "question_type": cls._map_question_type(question.question_type),
                **question_context,
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
                "policy": get_persona_policy(session.persona),
            },
            "prompt_version_id": None,
            "followup_context": cls._build_followup_context(
                selected_weakness_tag,
                question_context,
            ),
            "conversation_context": {
                "previous_question_count": previous_question_count,
                "previous_followup_count_for_parent": previous_followup_count,
            },
        }

    @staticmethod
    def _build_followup_context(selected_weakness_tag, question_context):
        raw_trigger = (
            selected_weakness_tag.get("tag_name")
            or selected_weakness_tag.get("weakness_tag_id")
            or selected_weakness_tag.get("code")
            or ""
        )
        trigger = str(raw_trigger).strip().upper().replace("-", "_").replace(" ", "_")
        technical_purposes = {
            "TECH_DEPTH_LOW": "technical_understanding",
            "WEAK_TECHNICAL_UNDERSTANDING": "technical_understanding",
            "MISSING_REASON": "technology_choice_reasoning",
            "WEAK_TECHNICAL_REASONING": "technology_choice_reasoning",
            "NO_ALTERNATIVE": "alternative_and_tradeoff_comparison",
            "WEAK_JD_LINK": "job_requirement_alignment",
            "WEAK_JD_FIT": "job_requirement_alignment",
        }
        return {
            **question_context,
            "trigger": trigger or None,
            "purpose": technical_purposes.get(trigger, "answer_clarification"),
        }

    @classmethod
    def _save_generation_metadata_tags(cls, question, generation_result, persona):
        metadata = {
            "generation_source": generation_result.get("generation_source")
            or ("openai" if cls._is_real_call_mode() else "mock"),
            "prompt_type": generation_result.get("prompt_type")
            or "follow_up_generation",
            "persona": normalize_persona_type(persona),
            "prompt_source": generation_result.get("prompt_source"),
            "prompt_template_id": generation_result.get("prompt_template_id"),
            "prompt_template_name": generation_result.get("prompt_template_name"),
            "prompt_version_id": generation_result.get("prompt_version_id"),
            "prompt_version_label": generation_result.get("prompt_version_label"),
            "is_active_prompt_version": generation_result.get(
                "is_active_prompt_version"
            ),
            "reason": generation_result.get("reason"),
        }
        QuestionSourceTag.objects.create(
            question=question,
            source_type="general",
            source_label="generation_metadata",
            source_text_excerpt=json.dumps(
                {
                    key: value
                    for key, value in metadata.items()
                    if value not in (None, "", [], {})
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            source_reference=question.source_reference or "",
        )

    @staticmethod
    def _map_question_type(question_type):
        if question_type == "follow_up":
            return "job"
        if question_type == "main":
            return "job"
        return question_type or "job"

    @staticmethod
    def _map_persona_type(persona):
        return normalize_persona_type(persona)

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
