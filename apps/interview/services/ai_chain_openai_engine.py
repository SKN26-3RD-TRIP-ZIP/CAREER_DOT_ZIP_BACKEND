"""
AI 면접 Chain OpenAI engine.

배치 위치:
apps/interview/services/ai_chain_openai_engine.py

역할:
- OpenAI 기반 AI Chain engine의 기본 구조 제공
- mock engine과 동일한 public method interface 유지
- 실제 프롬프트/파싱 고도화 전까지는 mock fallback을 사용해 기존 API 흐름을 깨지 않음
"""

from __future__ import annotations

from typing import Any, Callable

from django.conf import settings

from apps.interview.services.ai_chain_mock_engine import AIChainMockEngine
from apps.interview.services.ai_chain_response_parser import (
    parse_llm_json_list,
    parse_llm_json_object,
)


class AIChainOpenAIEngine:
    """OpenAI 기반 AI Chain engine 기본 클래스.

    현재 public method는 기존 안정성을 위해 mock fallback을 반환한다.
    실제 OpenAI 호출은 private helper로 먼저 준비하고, 후속 작업에서 각 Chain에 연결한다.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        fallback_engine: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
    ):
        self.model = model or getattr(
            settings,
            "INTERVIEW_AI_OPENAI_MODEL",
            "gpt-4o-mini",
        )
        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
        self.fallback_engine = fallback_engine or AIChainMockEngine()
        self.client_factory = client_factory
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
        """OpenAI 답변 충족도 판단 엔진 진입점.

        후속 작업에서 실제 OpenAI API 호출 및 JSON 파싱을 연결한다.
        현재는 기존 API 안정성을 위해 mock fallback 결과를 반환한다.
        """
        return self.fallback_engine.judge_answer_sufficiency(payload)

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
        """OpenAI Chat Completions API를 호출하고 message content를 반환한다.

        실제 Chain method에서는 이 결과를 _parse_response_object/list로 파싱해서 사용한다.
        """
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
        """OpenAI 응답을 JSON object로 파싱한다.

        실제 OpenAI API 연결 시 질문 생성, 답변 판단, 꼬리질문 생성 결과 파싱에 사용한다.
        """
        return parse_llm_json_object(raw_response, default=fallback or {})

    def _parse_response_list(
        self,
        raw_response: Any,
        fallback: list[Any] | None = None,
    ) -> list[Any]:
        """OpenAI 응답을 JSON list로 파싱한다.

        실제 OpenAI API 연결 시 list 형태 결과 파싱이 필요할 때 사용한다.
        """
        return parse_llm_json_list(raw_response, default=fallback or [])
