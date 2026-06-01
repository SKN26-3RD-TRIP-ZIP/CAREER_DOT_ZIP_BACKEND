from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CareerType = Literal["newcomer", "experienced"]
MajorType = Literal["major", "non_major"]
InterviewDepth = Literal["light", "deep", "real"]
PersonaId = Literal["coach", "practical", "critical"]

QuestionType = Literal[
    "project_experience",
    "technical_reasoning",
    "contribution_check",
    "problem_solving",
    "job_fit",
    "collaboration",
    "growth_learning",
    "fallback",
]

SourceType = Literal[
    "resume",
    "cover_letter",
    "jd",
    "resume_jd",
    "user_setting",
    "fallback",
]

Difficulty = Literal["easy", "medium", "hard"]


def normalize_korean_interview_question(value: str) -> str:
    """한국어 면접 질문 문장을 자연스럽게 정리한다.

    기존 방식은 "설명해 주세요.", "궁금합니다." 같은 요청형 문장 끝을
    강제로 "?"로 바꿨기 때문에 UI에서 "설명해 주세요?"처럼 어색하게 보일 수 있었다.

    이 함수는 의미상 질문/요청형 문장이면 그대로 허용하고,
    문장부호가 아예 없는 의문형 문장에만 ?를 보정한다.
    """

    cleaned = " ".join(value.strip().split())

    if not cleaned:
        raise ValueError("question은 비어 있을 수 없습니다.")

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

    # 질문 의도가 약해도 schema 단계에서는 실패시키지 않고 문장부호만 보정한다.
    # 실제 품질 판단은 quality_rules 또는 프롬프트 개선 단계에서 처리한다.
    return cleaned + "."


class QuestionGenerationRequest(BaseModel):
    """질문 생성 Chain 입력값."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)
    resume_text: str = Field(..., min_length=10)
    cover_letter_text: str | None = None
    jd_text: str | None = None

    career_type: CareerType
    major_type: MajorType
    target_job: str = Field(..., min_length=1)
    interview_depth: InterviewDepth = "light"
    persona_id: PersonaId = "practical"

    question_count: int = Field(default=3, ge=1, le=10)
    previous_questions: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class InterviewQuestion(BaseModel):
    """프론트/백엔드에 전달할 단일 면접 질문."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=10)
    question_type: QuestionType
    source_type: SourceType
    source_summary: str = Field(..., min_length=1)
    difficulty: Difficulty = "medium"
    intent: str = Field(..., min_length=1)
    expected_keywords: list[str] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def normalize_question_sentence(cls, value: str) -> str:
        return normalize_korean_interview_question(value)

    @field_validator("expected_keywords")
    @classmethod
    def expected_keywords_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("expected_keywords는 최소 1개 이상 필요합니다.")
        return value


class QuestionGenerationResult(BaseModel):
    """질문 생성 Chain 출력값."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    persona_id: PersonaId
    questions: list[InterviewQuestion]

    @model_validator(mode="after")
    def questions_must_not_be_empty(self) -> "QuestionGenerationResult":
        if not self.questions:
            raise ValueError("questions는 최소 1개 이상 필요합니다.")
        return self
