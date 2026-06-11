"""
AI 면접 Chain OpenAI engine.

배치 위치:
apps/interview/services/ai_chain_openai_engine.py

역할:
- OpenAI 기반 AI Chain engine의 기본 구조 제공
- mock engine과 동일한 public method interface 유지
- 실제 OpenAI 호출 실패 시 mock fallback으로 기존 API 흐름 유지
"""

from __future__ import annotations

from typing import Any, Callable

from django.conf import settings

from apps.interview.ai_chain_contracts import NextAction, QuestionType
from apps.interview.services.ai_chain_mock_engine import AIChainMockEngine
from apps.interview.services.ai_chain_openai_prompts import (
    build_answer_sufficiency_system_prompt,
    build_answer_sufficiency_user_prompt,
    build_followup_system_prompt,
    build_followup_user_prompt,
    build_question_generation_system_prompt,
    build_question_generation_user_prompt,
)
from apps.interview.services.ai_chain_response_parser import (
    parse_llm_json_list,
    parse_llm_json_object,
)


MAIN_QUESTION_TYPE = "main"

ALLOWED_QUESTION_SOURCE_TYPES = {
    "jd",
    "resume",
    "cover_letter",
    "project_experience",
    "general",
}

QUESTION_SOURCE_TYPE_ALIASES = {
    "jd": "jd",
    "job_description": "jd",
    "jobdescription": "jd",
    "resume": "resume",
    "cv": "resume",
    "cover_letter": "cover_letter",
    "coverletter": "cover_letter",
    "self_introduction": "cover_letter",
    "self_intro": "cover_letter",
    "project": "project_experience",
    "project_experience": "project_experience",
    "general": "general",
}

FOLLOWUP_ACTION_ALIASES = {
    "FOLLOWUP",
    "FOLLOW_UP",
    "FOLLOWUP_QUESTION",
    "FOLLOW_UP_QUESTION",
    "GENERATE",
    "GENERATE_FOLLOWUP",
    "GENERATE_FOLLOW_UP",
    "GENERATE_FOLLOWUP_QUESTION",
    "GENERATE_FOLLOW_UP_QUESTION",
    "NEEDS_FOLLOWUP",
    "NEEDS_FOLLOW_UP",
    "INSUFFICIENT",
    "NOT_SUFFICIENT",
}

NEXT_QUESTION_ACTION_ALIASES = {
    "NEXT",
    "NEXT_QUESTION",
    "PASS",
    "SKIP",
    "SUFFICIENT",
    "ENOUGH",
}

FOLLOWUP_TRIGGER_DEFINITIONS = {
    "TOO_SHORT": "The answer is too short to verify the candidate's actual experience.",
    "ABSTRACT_ANSWER": "The answer is abstract and lacks concrete evidence.",
    "MISSING_REASON": "The answer does not explain the reason or rationale.",
    "UNCLEAR_ROLE": "The candidate's own role is unclear.",
    "NO_RESULT": "The answer does not include a result or measurable outcome.",
    "TECH_DEPTH_LOW": "The technical explanation is too shallow.",
    "WEAK_JD_LINK": "The answer is weakly connected to the job description.",
    "STAR_MISSING": "The answer lacks a clear situation, task, action, and result structure.",
    "NO_ALTERNATIVE": "The answer does not compare alternatives or trade-offs.",
    "OFF_TOPIC": "The answer does not address the question.",
}

HIGH_SEVERITY_FOLLOWUP_TRIGGERS = {
    "OFF_TOPIC",
    "TECH_DEPTH_LOW",
    "MISSING_REASON",
    "UNCLEAR_ROLE",
    "NO_RESULT",
    "WEAK_JD_LINK",
}


class AIChainOpenAIError(RuntimeError):
    """OpenAI real call 실패를 명확히 전달하기 위한 예외."""

    def __init__(self, chain_name: str, message: str):
        self.chain_name = chain_name
        super().__init__(message)


class AIChainOpenAIEngine:
    """OpenAI 기반 AI Chain engine.

    기본값은 mock fallback을 사용한다.
    settings.INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=True 또는
    생성자 enable_real_call=True인 경우에만 실제 OpenAI 호출을 시도한다.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        fallback_engine: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
        enable_real_call: bool | None = None,
    ):
        self.model = model or getattr(
            settings,
            "INTERVIEW_AI_OPENAI_MODEL",
            "gpt-4o-mini",
        )
        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
        self.fallback_engine = fallback_engine or AIChainMockEngine()
        self.client_factory = client_factory
        self.enable_real_call = (
            enable_real_call
            if enable_real_call is not None
            else getattr(settings, "INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL", False)
        )
        self._client = None

    def get_personas(self) -> list[dict[str, Any]]:
        return self.fallback_engine.get_personas()

    def get_weakness_tags(self) -> list[dict[str, Any]]:
        return self.fallback_engine.get_weakness_tags()

    def generate_questions(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enable_real_call:
            return self.fallback_engine.generate_questions(payload)

        try:
            raw_response = self._request_text(
                system_prompt=build_question_generation_system_prompt(payload.get("persona")),
                user_prompt=build_question_generation_user_prompt(payload),
                temperature=0.3,
                max_tokens=1600,
            )
            parsed = self._parse_response_object(raw_response)

            if not parsed:
                raise ValueError("OpenAI question generation response is empty or invalid JSON.")

            return self._normalize_question_generation_result(
                parsed,
                payload=payload,
                fallback=None,
            )

        except Exception as exc:
            raise AIChainOpenAIError(
                "question_generation",
                "OpenAI 질문 생성에 실패했습니다. API Key, 모델 설정, 응답 JSON 형식을 확인해주세요.",
            ) from exc

    def judge_answer_sufficiency(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enable_real_call:
            return self.fallback_engine.judge_answer_sufficiency(payload)

        try:
            raw_response = self._request_text(
                system_prompt=build_answer_sufficiency_system_prompt(payload.get("persona")),
                user_prompt=build_answer_sufficiency_user_prompt(payload),
                temperature=0.1,
                max_tokens=1000,
            )
            parsed = self._parse_response_object(raw_response)

            if not parsed:
                raise ValueError("OpenAI sufficiency response is empty or invalid JSON.")

            normalized = self._normalize_sufficiency_result(
                parsed,
                fallback=None,
            )
            return self._apply_local_followup_guardrails(
                normalized,
                payload,
            )

        except Exception as exc:
            raise AIChainOpenAIError(
                "answer_sufficiency",
                "OpenAI 답변 충족도 판단에 실패했습니다. API Key, 모델 설정, 응답 JSON 형식을 확인해주세요.",
            ) from exc

    def generate_followup_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enable_real_call:
            return self.fallback_engine.generate_followup_question(payload)

        try:
            raw_response = self._request_text(
                system_prompt=build_followup_system_prompt(payload.get("persona")),
                user_prompt=build_followup_user_prompt(payload),
                temperature=0.3,
                max_tokens=800,
            )
            parsed = self._parse_response_object(raw_response)

            if not parsed:
                raise ValueError("OpenAI follow-up response is empty or invalid JSON.")

            return self._normalize_followup_result(
                parsed,
                payload=payload,
                fallback=None,
            )

        except Exception as exc:
            raise AIChainOpenAIError(
                "followup_generation",
                "OpenAI 꼬리질문 생성에 실패했습니다. API Key, 모델 설정, 응답 JSON 형식을 확인해주세요.",
            ) from exc

    def generate_followup_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.fallback_engine.generate_followup_mock(payload)

    def _fallback_or_raise(self, fallback: dict[str, Any] | None, message: str) -> dict[str, Any]:
        if fallback is not None:
            return fallback
        raise ValueError(message)

    def _get_client(self):
        """OpenAI client를 lazy initialization 방식으로 생성한다."""
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required to use AIChainOpenAIEngine.")

        if self.client_factory:
            self._client = self.client_factory(self.api_key)
            return self._client

        from openai import OpenAI

        self._client = OpenAI(api_key=self.api_key)
        return self._client

    def _request_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str:
        """OpenAI Chat Completions API를 호출하고 message content를 반환한다."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if not getattr(response, "choices", None):
            return ""

        message = response.choices[0].message
        return (getattr(message, "content", "") or "").strip()

    def _parse_response_object(
        self,
        raw_response: Any,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """OpenAI 응답을 JSON object로 파싱한다."""
        return parse_llm_json_object(raw_response, default=fallback or {})

    def _parse_response_list(
        self,
        raw_response: Any,
        fallback: list[Any] | None = None,
    ) -> list[Any]:
        """OpenAI 응답을 JSON list로 파싱한다."""
        return parse_llm_json_list(raw_response, default=fallback or [])

    def _normalize_question_generation_result(
        self,
        parsed: dict[str, Any],
        payload: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        """OpenAI 질문 생성 결과를 기존 service 계약에 맞게 보정한다."""
        if not isinstance(parsed, dict):
            return self._fallback_or_raise(fallback, "Invalid OpenAI question generation result.")

        questions = parsed.get("questions")
        if not isinstance(questions, list):
            return self._fallback_or_raise(fallback, "Invalid OpenAI question generation result.")

        options = payload.get("generation_options") or {}
        question_count = int(options.get("question_count") or len(questions) or 3)
        normalized_questions = []

        for index, question in enumerate(questions[:question_count], start=1):
            if not isinstance(question, dict):
                continue

            question_text = (question.get("question_text") or "").strip()
            if not question_text:
                continue

            source_tags = question.get("source_tags")
            if not isinstance(source_tags, list):
                source_tags = []

            normalized_source_tags = self._normalize_source_tags(source_tags)

            normalized_questions.append(
                {
                    "client_question_key": question.get("client_question_key") or f"q_{index:03d}",
                    "question_text": question_text,
                    "question_type": MAIN_QUESTION_TYPE,
                    "difficulty": question.get("difficulty"),
                    "order_index": int(question.get("order_index") or index),
                    "generation_reason": question.get(
                        "generation_reason",
                        "OpenAI engine 기반 질문 생성",
                    ),
                    "source_tags": normalized_source_tags,
                }
            )

        if not normalized_questions:
            return self._fallback_or_raise(fallback, "Invalid OpenAI question generation result.")

        return {
            "session_id": parsed.get("session_id", payload.get("session_id")),
            "questions": normalized_questions,
            "fallback_used": False,
        }
    
    def _normalize_question_source_type(self, source_type: Any) -> str:
        normalized_source_type = str(source_type or "general").strip().lower()
        return QUESTION_SOURCE_TYPE_ALIASES.get(normalized_source_type, "general")

    def _normalize_source_tags(self, source_tags: list[Any]) -> list[dict[str, Any]]:
        normalized = []

        for source_tag in source_tags:
            if not isinstance(source_tag, dict):
                continue

            source_type = self._normalize_question_source_type(source_tag.get("source_type"))
            normalized.append(
                {
                    "source_type": source_type,
                    "source_label": source_tag.get("source_label") or source_type,
                    "source_text_excerpt": source_tag.get("source_text_excerpt") or "",
                }
            )

        if normalized:
            return normalized

        return [
            {
                "source_type": "general",
                "source_label": "일반 질문",
                "source_text_excerpt": "",
            }
        ]

    def _normalize_sufficiency_result(
        self,
        parsed: dict[str, Any],
        fallback: dict[str, Any] | None,
    ) -> dict[str, Any]:
        fallback = fallback or {}

        if not isinstance(parsed, dict):
            return self._fallback_or_raise(
                fallback,
                "Invalid OpenAI answer sufficiency result.",
            )

        next_action = self._extract_next_action(parsed)
        if not next_action:
            return self._fallback_or_raise(fallback, "Invalid OpenAI question generation result.")

        answer_weakness_tags = self._normalize_weakness_tags(
            self._first_present(
                parsed,
                (
                    "answer_weakness_tags",
                    "weakness_tags",
                    "weakness_triggers",
                    "triggers",
                ),
                default=[],
            )
        )

        selected_weakness_tag = self._normalize_selected_weakness_tag(
            self._first_present(
                parsed,
                (
                    "selected_weakness_tag",
                    "selected_trigger",
                    "trigger",
                    "followup_trigger",
                    "follow_up_trigger",
                    "answer_judgement",
                    "answer_judgment",
                ),
            )
        )

        should_generate_followup = next_action == NextAction.GENERATE_FOLLOWUP.value
        parsed_is_sufficient = self._coerce_bool(
            self._first_present(
                parsed,
                (
                    "is_sufficient",
                    "answer_sufficient",
                    "sufficient",
                ),
            )
        )
        is_sufficient = (
            parsed_is_sufficient
            if parsed_is_sufficient is not None
            else not should_generate_followup
        )

        if should_generate_followup and selected_weakness_tag is None and answer_weakness_tags:
            first_tag = answer_weakness_tags[0]
            if isinstance(first_tag, dict):
                selected_weakness_tag = {
                    "weakness_tag_id": first_tag.get("weakness_tag_id"),
                    "tag_name": first_tag.get("tag_name"),
                    "reason": first_tag.get("reason"),
                }

        if should_generate_followup and selected_weakness_tag is None:
            selected_weakness_tag = self._build_weakness_tag(
                "ABSTRACT_ANSWER",
                "The model requested a follow-up but did not provide a selected weakness tag.",
            )
            answer_weakness_tags = [selected_weakness_tag]

        return {
            "answer_id": parsed.get("answer_id", fallback.get("answer_id")),
            "is_sufficient": is_sufficient,
            "sufficiency_reason": parsed.get(
                "sufficiency_reason",
                fallback.get("sufficiency_reason", ""),
            ),
            "answer_weakness_tags": answer_weakness_tags,
            "selected_weakness_tag": selected_weakness_tag,
            "should_generate_followup": should_generate_followup,
            "next_action": next_action,
        }

    @staticmethod
    def _first_present(
        source: dict[str, Any],
        keys: tuple[str, ...],
        default: Any = None,
    ) -> Any:
        for key in keys:
            if key in source and source.get(key) is not None:
                return source.get(key)
        return default

    @staticmethod
    def _coerce_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None:
            return None

        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        return None

    def _extract_next_action(self, parsed: dict[str, Any]) -> str | None:
        for key in (
            "next_action",
            "follow_up_decision",
            "followup_decision",
            "followup_action",
            "follow_up_action",
            "decision",
            "action",
        ):
            action = self._normalize_action(parsed.get(key))
            if action:
                return action

        should_generate_followup = self._coerce_bool(
            self._first_present(
                parsed,
                (
                    "should_generate_followup",
                    "should_generate_follow_up",
                    "generate_followup",
                    "generate_follow_up",
                    "needs_followup",
                    "needs_follow_up",
                ),
            )
        )
        if should_generate_followup is not None:
            return (
                NextAction.GENERATE_FOLLOWUP.value
                if should_generate_followup
                else NextAction.NEXT_QUESTION.value
            )

        is_sufficient = self._coerce_bool(
            self._first_present(
                parsed,
                (
                    "is_sufficient",
                    "answer_sufficient",
                    "sufficient",
                ),
            )
        )
        if is_sufficient is not None:
            return (
                NextAction.NEXT_QUESTION.value
                if is_sufficient
                else NextAction.GENERATE_FOLLOWUP.value
            )

        return None

    @staticmethod
    def _normalize_action(value: Any) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        if normalized == NextAction.GENERATE_FOLLOWUP.value:
            return NextAction.GENERATE_FOLLOWUP.value
        if normalized == NextAction.NEXT_QUESTION.value:
            return NextAction.NEXT_QUESTION.value
        if normalized in FOLLOWUP_ACTION_ALIASES:
            return NextAction.GENERATE_FOLLOWUP.value
        if normalized in NEXT_QUESTION_ACTION_ALIASES:
            return NextAction.NEXT_QUESTION.value
        return None

    def _normalize_weakness_tags(self, raw_tags: Any) -> list[dict[str, Any]]:
        if raw_tags is None:
            return []
        if isinstance(raw_tags, (str, dict)):
            raw_tags = [raw_tags]
        if not isinstance(raw_tags, list):
            return []

        normalized_tags = []
        for index, tag in enumerate(raw_tags, start=1):
            normalized = self._normalize_selected_weakness_tag(tag)
            if normalized:
                normalized["priority_rank"] = normalized.get("priority_rank") or index
                normalized_tags.append(normalized)
        return normalized_tags

    def _normalize_selected_weakness_tag(self, raw_tag: Any) -> dict[str, Any] | None:
        if raw_tag is None:
            return None

        if isinstance(raw_tag, str):
            return self._build_weakness_tag(raw_tag)

        if not isinstance(raw_tag, dict):
            return None

        trigger = (
            raw_tag.get("trigger")
            or raw_tag.get("tag_name")
            or raw_tag.get("name")
            or raw_tag.get("code")
            or raw_tag.get("weakness_tag_id")
        )
        if not trigger:
            return None

        normalized = self._build_weakness_tag(
            trigger,
            reason=raw_tag.get("reason") or raw_tag.get("description"),
        )
        normalized["weakness_tag_id"] = (
            raw_tag.get("weakness_tag_id")
            or raw_tag.get("answer_weakness_tag_id")
            or normalized["weakness_tag_id"]
        )
        return normalized

    @staticmethod
    def _normalize_trigger_name(value: Any) -> str:
        normalized = str(value or "ABSTRACT_ANSWER").strip().upper()
        normalized = normalized.replace("-", "_").replace(" ", "_")
        return normalized or "ABSTRACT_ANSWER"

    def _build_weakness_tag(self, trigger: Any, reason: str | None = None) -> dict[str, Any]:
        trigger_name = self._normalize_trigger_name(trigger)
        if trigger_name not in FOLLOWUP_TRIGGER_DEFINITIONS:
            trigger_name = "ABSTRACT_ANSWER"

        return {
            "weakness_tag_id": trigger_name,
            "tag_name": trigger_name,
            "reason": reason or FOLLOWUP_TRIGGER_DEFINITIONS[trigger_name],
        }

    def _apply_local_followup_guardrails(
        self,
        result: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        local_triggers = self._detect_local_followup_triggers(payload)

        if result.get("next_action") != NextAction.GENERATE_FOLLOWUP.value:
            if not local_triggers:
                return result
            return self._force_followup_result(result, local_triggers)

        if self._should_suppress_followup(result, payload, local_triggers):
            return {
                **result,
                "is_sufficient": True,
                "sufficiency_reason": (
                    "Answer has enough concrete situation, role, action, reason, "
                    "result, and job relevance to continue."
                ),
                "selected_weakness_tag": None,
                "should_generate_followup": False,
                "next_action": NextAction.NEXT_QUESTION.value,
            }

        return result

    def _force_followup_result(
        self,
        result: dict[str, Any],
        triggers: list[str],
    ) -> dict[str, Any]:
        weakness_tags = [
            self._build_weakness_tag(trigger)
            for trigger in triggers
        ]
        selected_weakness_tag = weakness_tags[0]

        return {
            **result,
            "is_sufficient": False,
            "sufficiency_reason": selected_weakness_tag["reason"],
            "answer_weakness_tags": weakness_tags,
            "selected_weakness_tag": selected_weakness_tag,
            "should_generate_followup": True,
            "next_action": NextAction.GENERATE_FOLLOWUP.value,
        }

    def _should_suppress_followup(
        self,
        result: dict[str, Any],
        payload: dict[str, Any],
        local_triggers: list[str],
    ) -> bool:
        signals = self._calculate_answer_sufficiency_signals(payload)
        if not signals["is_sufficient"]:
            return False

        llm_triggers = self._get_result_trigger_names(result)
        if not llm_triggers:
            return True

        local_trigger_set = set(local_triggers)
        high_severity_triggers = {
            trigger
            for trigger in llm_triggers
            if trigger in HIGH_SEVERITY_FOLLOWUP_TRIGGERS
        }
        if high_severity_triggers & local_trigger_set:
            return False

        return True

    def _get_result_trigger_names(self, result: dict[str, Any]) -> set[str]:
        trigger_names = set()

        def add_trigger(raw_trigger: Any) -> None:
            if raw_trigger is not None:
                trigger_names.add(self._normalize_trigger_name(raw_trigger))

        selected = result.get("selected_weakness_tag")
        if isinstance(selected, dict):
            add_trigger(selected.get("tag_name"))
            add_trigger(selected.get("weakness_tag_id"))

        for tag in result.get("answer_weakness_tags") or []:
            if not isinstance(tag, dict):
                continue
            add_trigger(tag.get("tag_name"))
            add_trigger(tag.get("weakness_tag_id"))

        trigger_names.discard("")
        return {trigger for trigger in trigger_names if trigger}

    def _calculate_answer_sufficiency_signals(self, payload: dict[str, Any]) -> dict[str, Any]:
        answer = payload.get("answer") or {}
        question = payload.get("question") or {}
        answer_text = str(answer.get("answer_text") or "").strip()
        question_text = str(question.get("question_text") or "").strip()
        source_tags = question.get("source_tags") or []
        source_text = " ".join(
            str(tag.get("source_text_excerpt") or "")
            for tag in source_tags
            if isinstance(tag, dict)
        )

        compact_answer = "".join(answer_text.split())
        normalized_answer = answer_text.lower()
        context_text = f"{question_text} {source_text}"

        too_short = len(compact_answer) < 40
        uncertainty = self._contains_any(
            normalized_answer,
            (
                "i do not know",
                "i don't know",
                "not sure",
                "잘 모르",
                "모르겠습니다",
                "그냥 했",
                "열심히 했",
            ),
        )

        technical_question = self._contains_any(
            context_text,
            (
                "기술",
                "api",
                "django",
                "mysql",
                "openai",
                "장애",
                "설계",
                "구현",
                "technical",
                "architecture",
                "backend",
            ),
        )
        technical_depth_count = self._count_markers(
            answer_text,
            (
                "api",
                "db",
                "sql",
                "django",
                "mysql",
                "openai",
                "transaction",
                "rollback",
                "retry",
                "cache",
                "queue",
                "orm",
                "index",
                "select_related",
                "prefetch_related",
                "redis",
                "query",
                "트랜잭션",
                "재시도",
                "롤백",
                "인덱스",
                "쿼리",
                "캐시",
                "백엔드",
                "장애",
                "구현",
                "설계",
            ),
        )

        signals = {
            "length_ok": len(compact_answer) >= 160,
            "direct_answer": not uncertainty and (
                technical_depth_count > 0
                or not technical_question
                or self._has_context_overlap(answer_text, context_text)
            ),
            "situation_or_problem": self._contains_any(
                answer_text,
                (
                    "상황",
                    "문제",
                    "원인",
                    "초기",
                    "장애",
                    "느린",
                    "느렸",
                    "실패",
                    "issue",
                    "problem",
                    "failure",
                    "latency",
                    "slow",
                ),
            ),
            "role_clear": self._contains_any(
                answer_text,
                (
                    "제가",
                    "저는",
                    "직접",
                    "담당",
                    "역할",
                    "주도",
                    "기여",
                    "i ",
                    "my ",
                    "implemented",
                    "designed",
                    "led",
                ),
            ),
            "concrete_action": self._contains_any(
                answer_text,
                (
                    "분석",
                    "적용",
                    "추가",
                    "구현",
                    "설계",
                    "분리",
                    "개선",
                    "확인",
                    "선택",
                    "검토",
                    "analyzed",
                    "applied",
                    "added",
                    "implemented",
                    "designed",
                    "separated",
                    "verified",
                ),
            ),
            "result_present": self._contains_any(
                answer_text,
                (
                    "결과",
                    "성과",
                    "지표",
                    "개선",
                    "감소",
                    "증가",
                    "줄",
                    "확인",
                    "초",
                    "%",
                    "result",
                    "improved",
                    "reduced",
                    "increased",
                    "from",
                    "to",
                ),
            ),
            "reason_present": self._contains_any(
                answer_text,
                (
                    "이유",
                    "때문",
                    "근거",
                    "선택",
                    "원인",
                    "because",
                    "why",
                    "reason",
                    "chose",
                ),
            ),
            "alternative_present": self._contains_any(
                answer_text,
                (
                    "대안",
                    "비교",
                    "검토",
                    "하지만",
                    "우선",
                    "대신",
                    "alternative",
                    "compared",
                    "tradeoff",
                    "instead",
                    "but",
                ),
            ),
            "technical_depth": technical_depth_count >= 2 if technical_question else True,
            "jd_link": (
                technical_depth_count > 0
                or self._has_context_overlap(answer_text, context_text)
                or not technical_question
            ),
            "not_abstract_only": len(compact_answer) >= 90 and technical_depth_count > 0,
            "off_topic": uncertainty or (
                technical_question
                and technical_depth_count == 0
                and not self._has_context_overlap(answer_text, context_text)
            ),
            "too_short": too_short,
        }

        positive_signal_keys = (
            "direct_answer",
            "situation_or_problem",
            "role_clear",
            "concrete_action",
            "result_present",
            "reason_present",
            "alternative_present",
            "technical_depth",
            "jd_link",
            "not_abstract_only",
        )
        score = sum(1 for key in positive_signal_keys if signals[key])
        signals["score"] = score
        signals["is_sufficient"] = (
            signals["length_ok"]
            and score >= 7
            and not signals["off_topic"]
            and not signals["too_short"]
        )
        return signals

    def _detect_local_followup_triggers(self, payload: dict[str, Any]) -> list[str]:
        signals = self._calculate_answer_sufficiency_signals(payload)
        triggers = []

        if signals["too_short"]:
            triggers.append("TOO_SHORT")

        if signals["off_topic"]:
            triggers.append("OFF_TOPIC")

        if not signals["not_abstract_only"] and not signals["too_short"]:
            triggers.append("ABSTRACT_ANSWER")

        if not signals["role_clear"]:
            triggers.append("UNCLEAR_ROLE")

        if not signals["result_present"]:
            triggers.append("NO_RESULT")

        if not signals["reason_present"]:
            triggers.append("MISSING_REASON")

        if not signals["technical_depth"]:
            triggers.append("TECH_DEPTH_LOW")

        if not signals["jd_link"]:
            triggers.append("WEAK_JD_LINK")

        if signals["score"] < 6 and not signals["too_short"]:
            triggers.append("STAR_MISSING")

        seen = set()
        unique_triggers = []
        for trigger in triggers:
            if trigger not in seen:
                seen.add(trigger)
                unique_triggers.append(trigger)
        return unique_triggers

    @staticmethod
    def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(str(marker).lower() in lowered for marker in markers)

    def _count_markers(self, text: str, markers: tuple[str, ...]) -> int:
        lowered = text.lower()
        return sum(1 for marker in markers if str(marker).lower() in lowered)

    def _has_context_overlap(self, answer_text: str, context_text: str) -> bool:
        if not context_text.strip():
            return False

        normalized_answer = answer_text.lower()
        normalized_context = context_text.lower()
        context_terms = {
            term.strip(".,;:()[]{}")
            for term in normalized_context.split()
            if len(term.strip(".,;:()[]{}")) >= 4
        }
        if not context_terms:
            return False

        return any(term in normalized_answer for term in context_terms)

    def _normalize_followup_result(
        self,
        parsed: dict[str, Any],
        payload: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        """OpenAI 꼬리질문 생성 결과를 기존 service 계약에 맞게 보정한다."""
        if not isinstance(parsed, dict):
            return self._fallback_or_raise(fallback, "Invalid OpenAI question generation result.")

        followup_question = parsed.get("followup_question")
        if not isinstance(followup_question, dict):
            return self._fallback_or_raise(fallback, "Invalid OpenAI question generation result.")

        question_text = (followup_question.get("question_text") or "").strip()
        if not question_text:
            return self._fallback_or_raise(fallback, "Invalid OpenAI question generation result.")

        parent_question = payload.get("parent_question") or {}
        answer = payload.get("answer") or {}
        selected_tag = payload.get("selected_weakness_tag") or {}
        context = payload.get("conversation_context") or {}

        previous_question_count = int(context.get("previous_question_count") or 1)
        previous_followup_count = int(context.get("previous_followup_count_for_parent") or 0)

        normalized_followup = {
            "parent_question_id": followup_question.get(
                "parent_question_id",
                parent_question.get("question_id"),
            ),
            "generated_from_answer_id": followup_question.get(
                "generated_from_answer_id",
                answer.get("answer_id"),
            ),
            "answer_weakness_tag_id": followup_question.get(
                "answer_weakness_tag_id",
                selected_tag.get("answer_weakness_tag_id"),
            ),
            "question_text": question_text,
            "question_type": followup_question.get(
                "question_type",
                parent_question.get("question_type") or QuestionType.JOB.value,
            ),
            "difficulty": followup_question.get("difficulty"),
            "order_index": int(
                followup_question.get("order_index")
                or previous_question_count + previous_followup_count + 1
            ),
            "generation_reason": followup_question.get(
                "generation_reason",
                f"{selected_tag.get('tag_name', '약점 태그')} 기준으로 생성됨",
            ),
        }

        return {
            "session_id": parsed.get("session_id", payload.get("session_id")),
            "followup_question": normalized_followup,
        }
