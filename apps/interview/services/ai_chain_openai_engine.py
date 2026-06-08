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

from typing import Any

from django.conf import settings

from apps.interview.services.ai_chain_mock_engine import AIChainMockEngine
from apps.interview.services.ai_chain_response_parser import (
    parse_llm_json_list,
    parse_llm_json_object,
)


class AIChainOpenAIEngine:
    """OpenAI 기반 AI Chain engine 기본 클래스.

    현재 단계에서는 engine 교체 구조를 먼저 고정하는 것이 목적이다.
    실제 OpenAI 호출, 프롬프트 구성, JSON 파싱은 후속 작업에서 확장한다.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        fallback_engine: Any | None = None,
    ):
        self.model = model or getattr(
            settings,
            "INTERVIEW_AI_OPENAI_MODEL",
            "gpt-4o-mini",
        )
        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
        self.fallback_engine = fallback_engine or AIChainMockEngine()

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
