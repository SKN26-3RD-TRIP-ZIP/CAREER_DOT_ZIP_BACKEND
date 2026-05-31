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
        """한국어 LLM 질문 문장을 서비스에서 쓰기 좋게 정리한다.

        기존에는 반드시 물음표/요?/까?로 끝나야 통과했지만,
        실제 LLM은 "궁금합니다.", "설명해 주세요."처럼
        면접 질문으로 자연스러운 평서형 요청 문장을 자주 생성한다.

        MVP에서는 이런 표현을 실패로 보지 않고,
        끝 문장부호만 질문형으로 보정한다.
        """

        cleaned = " ".join(value.strip().split())

        if not cleaned:
            raise ValueError("question은 비어 있을 수 없습니다.")

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
            "설명해주실 수 있나요?",
            "말씀해 주세요.",
            "말씀해 주세요",
            "말씀해주실 수 있나요?",
            "알려주세요.",
            "알려주세요",
            "공유해 주세요.",
            "공유해 주세요",
        )

        if cleaned.endswith(question_endings):
            return cleaned

        if cleaned.endswith(request_like_endings):
            return cleaned.rstrip(".") + "?"

        # 한국어 면접 질문은 종종 "~는지 설명해주세요" 형태로 끝난다.
        if "무엇" in cleaned or "어떻게" in cleaned or "왜" in cleaned or "어떤" in cleaned:
            return cleaned.rstrip(".") + "?"

        # 그래도 질문 의도가 약한 문장은 품질 검증 단계에서 잡도록
        # schema에서는 문장부호만 보정한다.
        return cleaned.rstrip(".") + "?"

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
