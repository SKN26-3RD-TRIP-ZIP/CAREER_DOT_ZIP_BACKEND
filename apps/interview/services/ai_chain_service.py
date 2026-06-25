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
from apps.interview.services.sufficiency_payload import (
    build_sufficiency_payload_from_answer,
)


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

    def evaluate_answer_sufficiency(self, answer) -> dict[str, Any]:
        payload = build_sufficiency_payload_from_answer(answer)
        result = self.judge_answer_sufficiency(payload)

        answer_weakness_tags = result.get("answer_weakness_tags")
        selected_weakness_tag = result.get("selected_weakness_tag")
        return {
            "answer_weakness_tags": (
                answer_weakness_tags
                if isinstance(answer_weakness_tags, list)
                else []
            ),
            "selected_weakness_tag": (
                selected_weakness_tag
                if isinstance(selected_weakness_tag, dict)
                else None
            ),
        }

    def generate_followup_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.generate_followup_question(payload)

    def generate_followup_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.generate_followup_mock(payload)
