from interview_ai_mvp_scaffold.chains.followup_generation_chain import generate_follow_ups
from interview_ai_mvp_scaffold.chains.question_generation_chain import generate_questions
from interview_ai_mvp_scaffold.data.mock_interview_data import (
    MOCK_EVALUATION,
    get_mock_document,
    get_mock_user,
)
from interview_ai_mvp_scaffold.schemas.followup_schema import FollowUpGenerationRequest
from interview_ai_mvp_scaffold.schemas.question_schema import QuestionGenerationRequest


def test_question_generation_mock():
    user = get_mock_user("user_001")
    doc = get_mock_document("user_001")

    request = QuestionGenerationRequest(
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

    result = generate_questions(request, mode="mock")

    assert result.user_id == "user_001"
    assert len(result.questions) == 3
    assert result.questions[0].question_type == "technical_reasoning"


def test_followup_generation_mock():
    request = FollowUpGenerationRequest(
        question_id=MOCK_EVALUATION["question_id"],
        question="Django를 선택한 이유는 무엇인가요?",
        answer=MOCK_EVALUATION["answer"],
        weaknesses=MOCK_EVALUATION["weaknesses"],
        missing_keywords=MOCK_EVALUATION["missing_keywords"],
        weakness_tags=MOCK_EVALUATION["weakness_tags"],
    )

    result = generate_follow_ups(request, mode="mock")

    assert result.question_id == "q_001"
    assert len(result.follow_ups) >= 1
    assert result.follow_ups[0].follow_up_type == "technical_reasoning"
