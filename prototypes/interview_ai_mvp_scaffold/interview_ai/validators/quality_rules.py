from __future__ import annotations

from interview_ai_mvp_scaffold.schemas.question_schema import InterviewQuestion


GENERIC_QUESTIONS = {
    "자기소개 해주세요.",
    "본인의 장점은 무엇인가요?",
    "지원 동기는 무엇인가요?",
}


def validate_question_quality(
    question: InterviewQuestion,
    previous_questions: list[str] | None = None,
) -> list[str]:
    """질문 품질을 rule-based로 간단히 점검한다.

    반환값:
        통과하면 빈 리스트, 실패하면 실패 이유 리스트.
    """

    previous_questions = previous_questions or []
    errors: list[str] = []

    if len(question.question.strip()) < 15:
        errors.append("질문이 너무 짧습니다.")

    if question.question in GENERIC_QUESTIONS:
        errors.append("너무 일반적인 질문입니다.")

    if question.question in previous_questions:
        errors.append("이전 질문과 중복됩니다.")

    if not question.source_summary.strip():
        errors.append("질문 근거 요약이 비어 있습니다.")

    if not question.expected_keywords:
        errors.append("기대 키워드가 비어 있습니다.")

    return errors
