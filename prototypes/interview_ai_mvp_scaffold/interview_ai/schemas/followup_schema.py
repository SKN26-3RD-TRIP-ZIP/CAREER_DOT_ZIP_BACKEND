from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from interview_ai_mvp_scaffold.schemas.evaluation_schema import WeaknessTag


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


def normalize_korean_question_sentence(value: str) -> str:
    """한국어 면접 질문/요청형 문장을 질문형으로 정리한다.

    LLM은 꼬리질문을 만들 때 아래처럼 자연스러운 요청형 문장을 자주 생성한다.
    - "... 설명해 주세요."
    - "... 말씀해 주세요."
    - "... 궁금합니다."

    의미상 질문이면 실패시키지 않고 끝 문장부호를 ?로 보정한다.
    """

    cleaned = " ".join(value.strip().split())

    if not cleaned:
        raise ValueError("질문 문장은 비어 있을 수 없습니다.")

    question_endings = (
        "?",
        "요?",
        "까?",
    )

    request_like_endings = (
        "궁금합니다.",
        "궁금합니다",
        "설명해 주세요.",
        "설명해 주세요",
        "설명해주세요.",
        "설명해주세요",
        "설명해주실 수 있나요?",
        "말씀해 주세요.",
        "말씀해 주세요",
        "말씀해주세요.",
        "말씀해주세요",
        "말씀해주실 수 있나요?",
        "알려주세요.",
        "알려주세요",
        "공유해 주세요.",
        "공유해 주세요",
        "제시해 주세요.",
        "제시해 주세요",
    )

    if cleaned.endswith(question_endings):
        return cleaned

    if cleaned.endswith(request_like_endings):
        return cleaned.rstrip(".") + "?"

    # 질문 의문사가 포함되어 있으면 질문 의도가 있다고 보고 보정한다.
    question_markers = ("무엇", "어떻게", "왜", "어떤", "어느", "얼마나", "누가", "언제")
    if any(marker in cleaned for marker in question_markers):
        return cleaned.rstrip(".") + "?"

    # 꼬리질문은 대부분 명령형 요청 문장도 질문으로 사용 가능하므로,
    # schema 단계에서는 문장부호만 보정하고 품질 판단은 별도 rule/prompt에서 처리한다.
    return cleaned.rstrip(".") + "?"


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
        return normalize_korean_question_sentence(value)


class FollowUpGenerationResult(BaseModel):
    """꼬리질문 생성 Chain 출력값."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., min_length=1)
    follow_ups: list[FollowUpQuestion] = Field(default_factory=list)
