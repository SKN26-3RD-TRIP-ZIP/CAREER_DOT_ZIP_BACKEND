"""페르소나 반영 품질 점검용 실행 파일.

위치:
- 프로젝트 루트/run_persona_quality_check.py

실행 전:
1. .env 파일에 OPENAI_API_KEY 설정
2. pip install -r requirements.txt
3. python run_persona_quality_check.py

목적:
- 동일한 사용자 입력 자료에 대해 persona_id만 변경했을 때
  질문 초점과 꼬리질문 방향이 실제로 달라지는지 확인한다.

기본 테스트:
- user_001 기준으로 coach / practical / critical 3개 페르소나 비교

선택 실행:
- 환경변수 PERSONA_TEST_USER_ID로 테스트 대상을 바꿀 수 있다.
  예: PERSONA_TEST_USER_ID=user_003 python run_persona_quality_check.py

주의:
- mode="llm"으로 실행되므로 실제 OpenAI API 비용이 발생할 수 있다.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from interview_ai.data.mock_interview_data import get_mock_document, get_mock_user
from interview_ai.services.interview_service import (
    create_follow_up_questions,
    create_interview_questions,
)


PERSONA_IDS = ["coach", "practical", "critical"]

PERSONA_LABELS = {
    "coach": "친절한 코치형",
    "practical": "실무 면접관형",
    "critical": "날카로운 검증형",
}


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
        "답변에서 구체적인 판단 기준과 결과 설명이 조금 더 필요함",
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


def build_question_payload(user: dict[str, Any], persona_id: str) -> dict[str, Any]:
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
        "persona_id": persona_id,
        "question_count": 3,
        "previous_questions": [],
        "missing_fields": doc["missing_fields"],
    }


def summarize_questions(question_result: dict[str, Any]) -> dict[str, Any]:
    questions = question_result.get("questions", [])

    return {
        "question_count": len(questions),
        "question_types": [question.get("question_type") for question in questions],
        "source_types": [question.get("source_type") for question in questions],
        "difficulties": [question.get("difficulty") for question in questions],
        "questions": [question.get("question") for question in questions],
        "intents": [question.get("intent") for question in questions],
        "expected_keywords": [
            question.get("expected_keywords", []) for question in questions
        ],
    }


def summarize_follow_ups(follow_up_result: dict[str, Any] | None) -> dict[str, Any]:
    if not follow_up_result:
        return {
            "follow_up_count": 0,
            "follow_up_types": [],
            "follow_up_questions": [],
            "trigger_reasons": [],
        }

    follow_ups = follow_up_result.get("follow_ups", [])

    return {
        "follow_up_count": len(follow_ups),
        "follow_up_types": [
            follow_up.get("follow_up_type") for follow_up in follow_ups
        ],
        "follow_up_questions": [
            follow_up.get("follow_up_question") for follow_up in follow_ups
        ],
        "trigger_reasons": [
            follow_up.get("trigger_reason") for follow_up in follow_ups
        ],
    }


def run_persona_case(user: dict[str, Any], persona_id: str) -> dict[str, Any]:
    question_payload = build_question_payload(user, persona_id)

    question_result = create_interview_questions(question_payload, mode="llm")
    questions = question_result.get("questions", [])

    follow_up_result: dict[str, Any] | None = None

    if questions:
        first_question = questions[0]
        answer = SAMPLE_ANSWERS.get(
            user["user_id"],
            "프로젝트에서 사용한 기술과 문제 해결 과정을 중심으로 답변했습니다.",
        )

        follow_up_payload = {
            "question_id": first_question["question_id"],
            "question": first_question["question"],
            "answer": answer,
            "persona_id": persona_id,
            "max_follow_ups": 2,
            **DEFAULT_WEAKNESS_PAYLOAD,
        }

        follow_up_result = create_follow_up_questions(follow_up_payload, mode="llm")

    return {
        "status": "success",
        "persona_id": persona_id,
        "persona_label": PERSONA_LABELS.get(persona_id, persona_id),
        "question_summary": summarize_questions(question_result),
        "follow_up_summary": summarize_follow_ups(follow_up_result),
        "question_result": question_result,
        "follow_up_result": follow_up_result,
    }


def run_persona_case_safely(user: dict[str, Any], persona_id: str) -> dict[str, Any]:
    try:
        return run_persona_case(user, persona_id)
    except Exception as exc:
        return {
            "status": "failed",
            "persona_id": persona_id,
            "persona_label": PERSONA_LABELS.get(persona_id, persona_id),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }


def print_persona_case(result: dict[str, Any]) -> None:
    persona_id = result["persona_id"]
    persona_label = result["persona_label"]

    print(f"\n--- Persona: {persona_id} / {persona_label} ---")

    if result["status"] == "failed":
        print("실패")
        print(f"에러 타입: {result.get('error_type')}")
        print(f"에러 메시지: {result.get('error_message')}")
        return

    question_summary = result["question_summary"]

    print(f"질문 개수: {question_summary['question_count']}")
    print(f"질문 유형: {question_summary['question_types']}")
    print(f"난이도: {question_summary['difficulties']}")
    print(f"근거 source: {question_summary['source_types']}")

    print("질문:")
    for idx, question in enumerate(question_summary["questions"], start=1):
        print(f"  {idx}. {question}")

    follow_up_summary = result["follow_up_summary"]

    print("꼬리질문:")
    for idx, follow_up in enumerate(follow_up_summary["follow_up_questions"], start=1):
        print(f"  {idx}. {follow_up}")


def main() -> None:
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY가 없습니다. 프로젝트 루트의 .env 파일에 API 키를 설정해주세요."
        )

    user_id = os.getenv("PERSONA_TEST_USER_ID", "user_001")
    user = get_mock_user(user_id)

    print("\n=== Persona Quality Check Start ===")
    print(f"테스트 사용자: {user['user_id']} / {user['name']}")

    persona_results: list[dict[str, Any]] = []

    for persona_id in PERSONA_IDS:
        result = run_persona_case_safely(user, persona_id)
        persona_results.append(result)
        print_persona_case(result)

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"persona_quality_results_{user_id}_{timestamp}.json"

    success_count = sum(
        1 for result in persona_results if result["status"] == "success"
    )
    failed_count = sum(
        1 for result in persona_results if result["status"] == "failed"
    )

    output_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "test_user": {
            "user_id": user["user_id"],
            "name": user["name"],
            "career_type": user["career_type"],
            "major_type": user["major_type"],
            "target_job": user["target_job"],
        },
        "persona_count": len(PERSONA_IDS),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": persona_results,
    }

    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== Persona Quality Check Summary ===")
    print(f"성공: {success_count}")
    print(f"실패: {failed_count}")
    print(f"저장 위치: {output_path}")


if __name__ == "__main__":
    main()
