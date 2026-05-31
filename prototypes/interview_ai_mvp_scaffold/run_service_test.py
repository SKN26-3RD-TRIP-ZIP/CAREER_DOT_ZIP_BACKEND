import json

from interview_ai.data.mock_interview_data import get_mock_document, get_mock_user
from interview_ai.services.interview_service import (
    create_follow_up_questions,
    create_interview_questions,
    run_single_turn_interview,
)


def main() -> None:
    user = get_mock_user("user_001")
    doc = get_mock_document("user_001")

    question_payload = {
        "user_id": user["user_id"],
        "resume_text": doc["resume_text"],
        "cover_letter_text": doc["cover_letter_text"],
        "jd_text": doc["jd_text"],
        "career_type": user["career_type"],
        "major_type": user["major_type"],
        "target_job": user["target_job"],
        "interview_depth": user["interview_depth"],
        "persona_id": user["persona_id"],
        "question_count": 3,
        "previous_questions": [],
        "missing_fields": doc["missing_fields"],
    }

    question_result = create_interview_questions(question_payload, mode="mock")

    print("\n=== Service: Question Generation ===")
    print(json.dumps(question_result, ensure_ascii=False, indent=2))

    first_question = question_result["questions"][0]

    follow_up_payload = {
        "question_id": first_question["question_id"],
        "question": first_question["question"],
        "answer": "팀원들이 Django를 써본 적이 있고 인증 기능이 있어서 빠르게 개발할 수 있다고 생각했습니다.",
        "persona_id": user["persona_id"],
        "weaknesses": [
            "FastAPI나 Flask와의 구체적인 비교가 부족함",
            "프로젝트 요구사항과 기술 선택을 연결하는 설명이 약함",
        ],
        "missing_keywords": ["대안 비교", "트레이드오프", "프로젝트 요구사항"],
        "weakness_tags": ["weak_technical_reasoning", "lack_of_specificity"],
        "max_follow_ups": 2,
    }

    follow_up_result = create_follow_up_questions(follow_up_payload, mode="mock")

    print("\n=== Service: Follow-up Generation ===")
    print(json.dumps(follow_up_result, ensure_ascii=False, indent=2))

    single_turn_result = run_single_turn_interview(
        {
            **question_payload,
            "answer": "팀원들이 Django를 써본 적이 있고 인증 기능이 있어서 빠르게 개발할 수 있다고 생각했습니다.",
        },
        mode="mock",
    )

    print("\n=== Service: Single Turn Interview ===")
    print(json.dumps(single_turn_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()