from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


WeaknessTag = Literal[
    "lack_of_specificity",
    "weak_technical_reasoning",
    "unclear_contribution",
    "missing_result",
    "weak_job_fit",
    "shallow_problem_solving",
    "missing_keywords",
    "unstructured_answer",
]


class AnswerEvaluationResult(BaseModel):
    """답변 평가 결과 mock/연동용 schema.

    평가 담당 파트에서 실제 Chain을 만들기 전까지,
    꼬리질문 생성 Chain 입력 mock으로 사용할 수 있다.
    """

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(..., min_length=1)
    question_id: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    score: int = Field(..., ge=1, le=5)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    weakness_tags: list[WeaknessTag] = Field(default_factory=list)

    @field_validator("weaknesses")
    @classmethod
    def low_score_requires_weaknesses(cls, value: list[str]) -> list[str]:
        # score와 함께 검증하려면 model_validator가 더 정확하지만,
        # MVP에서는 필드 구조 검증만 우선 수행한다.
        return value
