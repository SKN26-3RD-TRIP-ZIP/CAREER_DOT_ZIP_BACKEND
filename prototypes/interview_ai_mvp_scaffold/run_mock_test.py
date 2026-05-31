import json

from interview_ai.chains.followup_generation_chain import generate_follow_ups
from interview_ai.chains.question_generation_chain import generate_questions
from interview_ai.data.mock_interview_data import (
    MOCK_EVALUATION,
    get_mock_document,
    get_mock_user,
)
from interview_ai.schemas.followup_schema import FollowUpGenerationRequest
from interview_ai.schemas.question_schema import QuestionGenerationRequest


def main() -> None:
    user = get_mock_user("user_001")
    doc = get_mock_document("user_001")

    question_request = QuestionGenerationRequest(
        user_id=user["user_id"],
        resume_text=doc["resume_text"],
        cover_letter_text=doc["cover_letter_text"],
        jd_text=doc["jd_text"],
        career_type=user["career_type"],
        major_type=user["major_type"],
        target_job=user["target_job"],
        interview_depth=user["interview_depth"],
        persona_id=user["persona_id"],
        missing_fields=doc["missing_fields"],
    )

    question_result = generate_questions(question_request, mode="mock")

    print("\n=== Question Generation Result ===")
    print(json.dumps(question_result.model_dump(), ensure_ascii=False, indent=2))

    first_question = question_result.questions[0]

    followup_request = FollowUpGenerationRequest(
        question_id=first_question.question_id,
        question=first_question.question,
        answer=MOCK_EVALUATION["answer"],
        weaknesses=MOCK_EVALUATION["weaknesses"],
        missing_keywords=MOCK_EVALUATION["missing_keywords"],
        weakness_tags=MOCK_EVALUATION["weakness_tags"],
    )

    followup_result = generate_follow_ups(followup_request, mode="mock")

    print("\n=== Follow-up Generation Result ===")
    print(json.dumps(followup_result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
