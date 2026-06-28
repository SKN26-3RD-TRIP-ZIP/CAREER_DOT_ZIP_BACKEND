from django.db import transaction

from apps.interview.models import (
    InterviewQuestion,
    InterviewSession,
    QuestionSourceTag,
)
from apps.report.services.recommendation_service import (
    get_session_weakness_recommended_questions,
)


class PracticeSessionCreationError(Exception):
    def __init__(self, detail, code):
        super().__init__(detail)
        self.detail = detail
        self.code = code


def _question_category(question_type):
    if question_type in {"technical", "personality"}:
        return question_type
    return "general"


def create_practice_session(
    *,
    source_session,
    question_count,
    persona=None,
    interview_mode=None,
):
    recommendation_result = get_session_weakness_recommended_questions(
        source_session,
        total_limit=question_count,
    )
    recommended_questions = recommendation_result.get("recommended_questions") or []

    if not recommended_questions:
        raise PracticeSessionCreationError(
            "No weakness-based practice questions are available for this session.",
            "PRACTICE_RECOMMENDATIONS_NOT_FOUND",
        )
    if len(recommended_questions) < question_count:
        raise PracticeSessionCreationError(
            (
                f"Only {len(recommended_questions)} practice question(s) are "
                f"available; {question_count} were requested."
            ),
            "INSUFFICIENT_PRACTICE_RECOMMENDATIONS",
        )

    selected_questions = recommended_questions[:question_count]

    with transaction.atomic():
        practice_session = InterviewSession.objects.create(
            user=source_session.user,
            jd=source_session.jd,
            resume=source_session.resume,
            cover_letter=source_session.cover_letter,
            interview_type=source_session.interview_type,
            persona=persona or source_session.persona or "practical",
            interview_mode=interview_mode or source_session.interview_mode or "text",
            status="created",
            total_question_count=question_count,
        )

        questions = []
        source_tags = []
        for order_index, recommendation in enumerate(selected_questions, start=1):
            question_bank_id = recommendation.get("question_bank_id")
            source_reference = (
                f"question_bank:{question_bank_id}"
                if question_bank_id
                else f"recommendation:{source_session.id}:{order_index}"
            )
            question = InterviewQuestion(
                session=practice_session,
                order_index=order_index,
                question_type="main",
                question_category=_question_category(
                    recommendation.get("question_type")
                ),
                question_text=recommendation.get("question_text") or "",
                difficulty=recommendation.get("difficulty") or "medium",
                source_type="question_bank" if question_bank_id else "general",
                source_reference=source_reference[:100],
            )
            questions.append(question)

        InterviewQuestion.objects.bulk_create(questions)

        for question, recommendation in zip(questions, selected_questions):
            source_tags.append(
                QuestionSourceTag(
                    question=question,
                    source_type=question.source_type,
                    source_label="weakness_recommendation",
                    source_text_excerpt=recommendation.get("weakness_tag") or "",
                    source_reference=question.source_reference or "",
                )
            )
        QuestionSourceTag.objects.bulk_create(source_tags)

    return {
        "session": practice_session,
        "questions": questions,
        "weakness_tags": recommendation_result.get("weakness_tags") or [],
    }
