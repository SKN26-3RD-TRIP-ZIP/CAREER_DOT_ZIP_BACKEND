"""LLM 질문 생성 품질 점검용 실행 파일.

위치:
- 프로젝트 루트/run_llm_quality_check.py

실행 전:
1. .env 파일에 OPENAI_API_KEY 설정
2. pip install -r requirements.txt
3. python run_llm_quality_check.py

주의:
- mode="llm"으로 실행되므로 실제 OpenAI API 비용이 발생할 수 있다.
- user_001, user_002, user_003 세 케이스를 한 번에 돌린다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from interview_ai.data.mock_interview_data import MOCK_USERS, get_mock_document
from interview_ai.services.interview_service import (
    create_follow_up_questions,
    create_interview_questions,
)


SAMPLE_ANSWERS: dict[str, str] = {
    "user_001": (
        "Django REST Framework를 선택한 이유는 팀원들이 이미 Django에 익숙했고, "
        "인증과 관리자 기능을 빠르게 구현할 수 있었기 때문입니다. "
        "다만 FastAPI와 비교했을 때 비동기 처리나 경량 API 측면에서는 아쉬움이 있을 수 있다고 생각합니다."
    ),
    "user_002": (
        "RFM 유사 피처는 사용자의 최근 이용 여부, 사용 빈도, 이용량을 반영하려고 만들었습니다. "
        "이탈 가능성이 높은 사용자는 접속 빈도가 줄고 스킵 비율이 높을 것이라고 생각했습니다."
    ),
    "user_003": (
        "RAG 검색 품질이 낮았던 이유는 chunk 단위가 너무 크거나 질문과 관련 없는 문서가 함께 검색되었기 때문입니다. "
        "그래서 chunk 크기를 조정하고 reranking을 추가해서 질문과 더 직접적으로 관련 있는 문서를 우선 사용하도록 했습니다."
    ),
}


DEFAULT_WEAKNESS_PAYLOAD: dict[str, Any] = {
    "weaknesses": [
        "기술 선택 이유나 개선 기준이 조금 더 구체적으로 설명될 필요가 있음",
    ],
    "missing_keywords": [
        "대안 비교",
        "트레이드오프",
        "정량적 결과",
    ],
    "weakness_tags": [
        "weak_technical_reasoning",
        "lack_of_specificity",
    ],
}


def build_question_payload(user: dict[str, Any]) -> dict[str, Any]:
    doc = get_mock_document(user["user_id"])

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
    }


def summarize_question_quality(question_result: dict[str, Any]) -> dict[str, Any]:
    questions = question_result.get("questions", [])

    return {
        "question_count": len(questions),
        "question_types": [question.get("question_type") for question in questions],
        "source_types": [question.get("source_type") for question in questions],
        "has_expected_keywords": [
            bool(question.get("expected_keywords")) for question in questions
        ],
        "has_source_summary": [
            bool(question.get("source_summary")) for question in questions
        ],
        "questions": [question.get("question") for question in questions],
    }


def run_case(user: dict[str, Any]) -> dict[str, Any]:
    user_id = user["user_id"]
    question_payload = build_question_payload(user)

    question_result = create_interview_questions(question_payload, mode="llm")
    questions = question_result.get("questions", [])

    follow_up_result: dict[str, Any] | None = None

    if questions:
        first_question = questions[0]
        answer = SAMPLE_ANSWERS.get(
            user_id,
            "해당 경험에서 사용한 기술과 문제 해결 과정을 중심으로 답변했습니다.",
        )

        follow_up_payload = {
            "question_id": first_question["question_id"],
            "question": first_question["question"],
            "answer": answer,
            "persona_id": user["persona_id"],
            "max_follow_ups": 2,
            **DEFAULT_WEAKNESS_PAYLOAD,
        }

        follow_up_result = create_follow_up_questions(follow_up_payload, mode="llm")

    return {
        "user_id": user_id,
        "user_name": user.get("name"),
        "career_type": user.get("career_type"),
        "major_type": user.get("major_type"),
        "target_job": user.get("target_job"),
        "persona_id": user.get("persona_id"),
        "question_quality_summary": summarize_question_quality(question_result),
        "question_result": question_result,
        "follow_up_result": follow_up_result,
    }


def main() -> None:
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY가 없습니다. 프로젝트 루트의 .env 파일에 API 키를 설정해주세요."
        )

    results: list[dict[str, Any]] = []

    print("\n=== LLM Quality Check Start ===")

    for user in MOCK_USERS:
        print(f"\n--- Running case: {user['user_id']} / {user['name']} ---")
        result = run_case(user)
        results.append(result)

        summary = result["question_quality_summary"]

        print(f"질문 개수: {summary['question_count']}")
        print(f"질문 유형: {summary['question_types']}")
        print(f"근거 source: {summary['source_types']}")

        for idx, question in enumerate(summary["questions"], start=1):
            print(f"{idx}. {question}")

        follow_up_result = result.get("follow_up_result")
        if follow_up_result:
            follow_ups = follow_up_result.get("follow_ups", [])
            print("꼬리질문:")
            for idx, follow_up in enumerate(follow_ups, start=1):
                print(f"  {idx}. {follow_up.get('follow_up_question')}")

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"llm_quality_results_{timestamp}.json"

    output_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "case_count": len(results),
        "results": results,
    }

    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n=== Saved result: {output_path} ===")


if __name__ == "__main__":
    main()
