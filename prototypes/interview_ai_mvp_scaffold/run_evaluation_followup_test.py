"""평가 결과 기반 꼬리질문 생성 테스트.

위치:
- 프로젝트 루트/run_evaluation_followup_test.py

실행:
- mock mode: python run_evaluation_followup_test.py
- llm mode:  EVALUATION_FOLLOWUP_MODE=llm python run_evaluation_followup_test.py

목적:
- 평가 결과의 weaknesses, missing_keywords, weakness_tags가
  꼬리질문 생성에 정상적으로 연결되는지 확인한다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from interview_ai.data.mock_interview_data import get_mock_document, get_mock_user
from interview_ai.services.interview_service import (
    create_follow_up_questions_from_evaluation,
    run_single_turn_interview_with_evaluation,
)


def build_question_payload() -> dict:
    user = get_mock_user("user_001")
    doc = get_mock_document("user_001")

    return {
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
        "answer": (
            "팀원들이 Django를 써본 적이 있고 인증 기능을 빠르게 구현할 수 있어서 "
            "Django REST Framework를 선택했습니다."
        ),
        "evaluation_result": {
            "evaluation_id": "eval_001",
            "question_id": "q_001",
            "answer": (
                "팀원들이 Django를 써본 적이 있고 인증 기능을 빠르게 구현할 수 있어서 "
                "Django REST Framework를 선택했습니다."
            ),
            "score": 3,
            "strengths": [
                "Django 선택 이유로 개발 속도와 인증 기능을 언급함",
                "팀 상황을 고려한 기술 선택이었다는 점을 설명함",
            ],
            "weaknesses": [
                "FastAPI나 Flask와의 구체적인 비교가 부족함",
                "프로젝트 요구사항과 기술 선택을 연결하는 설명이 약함",
            ],
            "missing_keywords": [
                "대안 비교",
                "트레이드오프",
                "프로젝트 요구사항",
            ],
            "weakness_tags": [
                "weak_technical_reasoning",
                "lack_of_specificity",
            ],
        },
    }


def run_direct_followup_test(mode: str) -> dict:
    payload = {
        "question_id": "q_001",
        "question": "Django REST Framework를 선택한 이유와 프로젝트에 기여한 점을 설명해 주세요.",
        "answer": (
            "팀원들이 Django를 써본 적이 있고 인증 기능을 빠르게 구현할 수 있어서 "
            "Django REST Framework를 선택했습니다."
        ),
        "persona_id": "practical",
        "max_follow_ups": 2,
        "evaluation_result": {
            "evaluation_id": "eval_direct_001",
            "question_id": "q_001",
            "answer": (
                "팀원들이 Django를 써본 적이 있고 인증 기능을 빠르게 구현할 수 있어서 "
                "Django REST Framework를 선택했습니다."
            ),
            "score": 3,
            "strengths": [
                "기술 선택 이유를 일부 설명함",
            ],
            "weaknesses": [
                "대안 비교가 부족함",
                "프로젝트 요구사항과 연결이 약함",
            ],
            "missing_keywords": [
                "FastAPI",
                "Flask",
                "트레이드오프",
                "프로젝트 요구사항",
            ],
            "weakness_tags": [
                "weak_technical_reasoning",
                "lack_of_specificity",
            ],
        },
    }

    return create_follow_up_questions_from_evaluation(payload, mode=mode)


def main() -> None:
    load_dotenv()

    mode = os.getenv("EVALUATION_FOLLOWUP_MODE", "mock")

    if mode == "llm" and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY가 없습니다. .env 파일에 API 키를 설정해주세요."
        )

    print("\n=== Evaluation Follow-up Test Start ===")
    print(f"mode: {mode}")

    direct_result = run_direct_followup_test(mode)

    print("\n=== Direct Evaluation Follow-up Result ===")
    print(json.dumps(direct_result, ensure_ascii=False, indent=2))

    single_turn_payload = build_question_payload()
    single_turn_result = run_single_turn_interview_with_evaluation(
        single_turn_payload,
        mode=mode,
    )

    print("\n=== Single Turn with Evaluation Result ===")
    print(json.dumps(single_turn_result, ensure_ascii=False, indent=2))

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"evaluation_followup_results_{timestamp}.json"

    output_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "direct_result": direct_result,
        "single_turn_result": single_turn_result,
    }

    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n저장 위치: {output_path}")


if __name__ == "__main__":
    main()
