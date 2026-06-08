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

import json
from typing import Any, Callable

from django.conf import settings

from apps.interview.ai_chain_contracts import (
    DEFAULT_WEAKNESS_TAG_CANDIDATES,
    NextAction,
)
from apps.interview.services.ai_chain_mock_engine import AIChainMockEngine
from apps.interview.services.ai_chain_response_parser import (
    parse_llm_json_list,
    parse_llm_json_object,
)


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
        """OpenAI 질문 생성 엔진 진입점.

        후속 작업에서 실제 OpenAI API 호출 및 JSON 파싱을 연결한다.
        현재는 기존 API 안정성을 위해 mock fallback 결과를 반환한다.
        """
        return self.fallback_engine.generate_questions(payload)

    def judge_answer_sufficiency(self, payload: dict[str, Any]) -> dict[str, Any]:
        """답변 충족도 판단.

        enable_real_call=True일 때 OpenAI 호출을 시도한다.
        호출 실패, JSON 파싱 실패, 필수 필드 누락 시 mock fallback을 반환한다.
        """
        fallback = self.fallback_engine.judge_answer_sufficiency(payload)
        if not self.enable_real_call:
            return fallback

        try:
            raw_response = self._request_text(
                system_prompt=self._build_answer_sufficiency_system_prompt(),
                user_prompt=self._build_answer_sufficiency_user_prompt(payload),
                temperature=0.1,
                max_tokens=1000,
            )
            parsed = self._parse_response_object(raw_response, fallback=fallback)
            return self._normalize_sufficiency_result(parsed, fallback=fallback)
        except Exception:
            return fallback

    def generate_followup_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        """OpenAI 꼬리질문 생성 엔진 진입점.

        후속 작업에서 실제 OpenAI API 호출 및 JSON 파싱을 연결한다.
        현재는 기존 API 안정성을 위해 mock fallback 결과를 반환한다.
        """
        return self.fallback_engine.generate_followup_question(payload)

    def generate_followup_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.fallback_engine.generate_followup_mock(payload)

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

    def _build_answer_sufficiency_system_prompt(self) -> str:
        return (
            "당신은 IT 직무 모의면접 답변 평가 엔진입니다. "
            "반드시 JSON object만 반환하세요. "
            "필드는 answer_id, is_sufficient, sufficiency_reason, "
            "answer_weakness_tags, selected_weakness_tag, should_generate_followup, next_action을 포함해야 합니다. "
            "next_action은 NEXT_QUESTION 또는 GENERATE_FOLLOWUP 중 하나여야 합니다."
        )

    def _build_answer_sufficiency_user_prompt(self, payload: dict[str, Any]) -> str:
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

    def _normalize_sufficiency_result(
        self,
        parsed: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        """OpenAI 답변 충족도 판단 결과를 기존 service 계약에 맞게 보정한다."""
        if not isinstance(parsed, dict):
            return fallback

        next_action = parsed.get("next_action")
        if next_action not in {
            NextAction.NEXT_QUESTION.value,
            NextAction.GENERATE_FOLLOWUP.value,
        }:
            return fallback

        answer_weakness_tags = parsed.get("answer_weakness_tags")
        if not isinstance(answer_weakness_tags, list):
            answer_weakness_tags = []

        selected_weakness_tag = parsed.get("selected_weakness_tag")
        if selected_weakness_tag is not None and not isinstance(selected_weakness_tag, dict):
            selected_weakness_tag = None

        should_generate_followup = next_action == NextAction.GENERATE_FOLLOWUP.value
        is_sufficient = bool(parsed.get("is_sufficient", not should_generate_followup))

        if should_generate_followup and selected_weakness_tag is None and answer_weakness_tags:
            first_tag = answer_weakness_tags[0]
            if isinstance(first_tag, dict):
                selected_weakness_tag = {
                    "weakness_tag_id": first_tag.get("weakness_tag_id"),
                    "tag_name": first_tag.get("tag_name"),
                    "reason": first_tag.get("reason"),
                }

        if should_generate_followup and selected_weakness_tag is None:
            return fallback

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
