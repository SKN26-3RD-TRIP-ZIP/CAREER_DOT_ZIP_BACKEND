from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from interview_ai.schemas.evaluation_schema import WeaknessTag


PersonaId = Literal["coach", "practical", "critical"]

FollowUpType = Literal[
    "specificity_check",
    "technical_reasoning",
    "contribution_check",
    "result_check",
    "job_fit_check",
    "problem_solving_deepening",
    "answer_structure",
]


def normalize_korean_follow_up_question(value: str) -> str:
    """한국어 꼬리질문 문장을 자연스럽게 정리한다.

    "설명해 주세요.", "말씀해 주세요.", "궁금합니다." 같은 요청형 문장은
    실제 면접에서 자연스럽게 쓰일 수 있으므로 강제로 ?를 붙이지 않는다.
    """

    cleaned = " ".join(value.strip().split())

    if not cleaned:
        raise ValueError("follow_up_question은 비어 있을 수 없습니다.")

    natural_endings = (
        "?",
        ".",
        "요",
        "까",
        "까?",
        "나요",
        "나요?",
        "습니까",
        "습니까?",
        "주세요",
        "주세요.",
        "주실 수 있나요",
        "주실 수 있나요?",
        "궁금합니다",
        "궁금합니다.",
    )

    if cleaned.endswith(natural_endings):
        return cleaned

    question_markers = ("무엇", "어떻게", "왜", "어떤", "어느", "얼마나", "누가", "언제")
    if any(marker in cleaned for marker in question_markers):
        return cleaned + "?"

    # 꼬리질문은 요청형 문장도 허용하므로 schema에서는 과도하게 실패시키지 않는다.
    return cleaned + "."


class FollowUpGenerationRequest(BaseModel):
    """꼬리질문 생성 Chain 입력값.

    A안에서는 question + answer 기반으로 생성하고,
    B안부터 evaluation_result를 함께 넘기는 구조로 확장한다.
    """

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=10)
    answer: str = Field(..., min_length=1)
    persona_id: PersonaId = "practical"

    weaknesses: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    weakness_tags: list[WeaknessTag] = Field(default_factory=list)

    max_follow_ups: int = Field(default=2, ge=0, le=3)


class FollowUpQuestion(BaseModel):
    """프론트/백엔드에 전달할 단일 꼬리질문."""

    model_config = ConfigDict(extra="forbid")

    follow_up_id: str = Field(..., min_length=1)
    question_id: str = Field(..., min_length=1)
    follow_up_question: str = Field(..., min_length=10)
    follow_up_type: FollowUpType
    trigger_reason: str = Field(..., min_length=1)
    based_on_weakness_tags: list[WeaknessTag] = Field(default_factory=list)

    @field_validator("follow_up_question")
    @classmethod
    def normalize_follow_up_question(cls, value: str) -> str:
        return normalize_korean_follow_up_question(value)


class FollowUpGenerationResult(BaseModel):
    """꼬리질문 생성 Chain 출력값."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., min_length=1)
    follow_ups: list[FollowUpQuestion] = Field(default_factory=list)
