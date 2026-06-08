"""
AI 면접 Chain service.

배치 위치:
apps/interview/services/ai_chain_service.py

역할:
- 외부 호출부가 사용하는 공통 service interface 제공
- 기본 구현은 engine factory를 통해 선택
- 추후 OpenAI/Claude engine으로 교체하더라도 호출부 변경을 최소화
"""

from __future__ import annotations

from typing import Any

from apps.interview.services.ai_chain_engine_factory import get_ai_chain_engine


class InterviewAIChainService:
    """AI Chain 외부 호출용 service wrapper."""

    def __init__(self, engine: Any | None = None, engine_name: str | None = None):
        self.engine = engine or get_ai_chain_engine(engine_name)

    def get_personas(self) -> list[dict[str, Any]]:
        return self.engine.get_personas()

    def get_weakness_tags(self) -> list[dict[str, Any]]:
        return self.engine.get_weakness_tags()

    def generate_questions(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.generate_questions(payload)

    def judge_answer_sufficiency(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.judge_answer_sufficiency(payload)

    def generate_followup_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.generate_followup_question(payload)

    def generate_followup_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.generate_followup_mock(payload)
