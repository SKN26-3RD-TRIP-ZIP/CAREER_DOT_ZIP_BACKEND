"""Question category resolution for evaluation/report.

This module is a compatibility layer owned by evaluation/report.
If InterviewQuestion.question_category exists, that field is the source of truth.
Until then, we infer a conservative category from existing session/question data
without changing the interview app schema.
"""

from __future__ import annotations

import re

VALID_QUESTION_CATEGORIES = {"technical", "personality", "general"}

_TECHNICAL_PATTERN = re.compile(
    r"("
    r"api|db|sql|redis|django|fastapi|react|vue|node|python|java|spring|"
    r"docker|kubernetes|aws|gcp|azure|ci/cd|rest|graphql|orm|llm|"
    r"아키텍처|서버|백엔드|프론트엔드|데이터베이스|쿼리|인덱스|캐시|"
    r"트랜잭션|동시성|성능|최적화|트래픽|장애|버그|배포|보안|"
    r"알고리즘|자료구조|파이프라인|마이그레이션|레이트\s*리밋"
    r")",
    re.IGNORECASE,
)

_PERSONALITY_PATTERN = re.compile(
    r"("
    r"협업|갈등|소통|리더십|강점|약점|가치관|동기|성장|실패|"
    r"스트레스|마감|팀원|책임감|오너십|성격|커뮤니케이션|"
    r"배운\s*점|어려웠던\s*점"
    r")",
    re.IGNORECASE,
)


def _normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().lower()
    if normalized in VALID_QUESTION_CATEGORIES:
        return normalized
    if normalized in {"job", "experience", "behavioral"}:
        return "general"
    return None


def resolve_question_category(answer) -> str:
    """Return technical/personality/general for an InterviewAnswer.

    Priority:
      1. question.question_category if the interview app provides it.
      2. session.interview_type for single-purpose sessions.
      3. question text heuristic for comprehensive/legacy data.
      4. technical fallback to preserve old scoring for unknown legacy data.
    """
    question = getattr(answer, "question", None)
    session = getattr(answer, "session", None) or getattr(question, "session", None)

    explicit = _normalize_category(getattr(question, "question_category", None))
    if explicit:
        return explicit

    session_type = _normalize_category(getattr(session, "interview_type", None))
    if session_type in {"technical", "personality"}:
        return session_type

    question_text = str(getattr(question, "question_text", "") or "")
    if _TECHNICAL_PATTERN.search(question_text):
        return "technical"
    if _PERSONALITY_PATTERN.search(question_text):
        return "personality"

    source_type = str(getattr(question, "source_type", "") or "").lower()
    if source_type in {"profile", "rule", "general"}:
        return "personality"

    return "technical"
