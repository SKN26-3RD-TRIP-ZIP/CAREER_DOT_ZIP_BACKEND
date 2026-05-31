from __future__ import annotations

from typing import Any, Literal

from interview_ai_mvp_scaffold.chains.followup_generation_chain import generate_follow_ups
from interview_ai_mvp_scaffold.chains.question_generation_chain import generate_questions
from interview_ai_mvp_scaffold.schemas.followup_schema import FollowUpGenerationRequest
from interview_ai_mvp_scaffold.schemas.question_schema import QuestionGenerationRequest


RunMode = Literal["mock", "llm"]


class InterviewServiceError(ValueError):
    """Interview service layer에서 발생하는 예외."""


def create_interview_questions(
    payload: dict[str, Any],
    *,
    mode: RunMode = "mock",
) -> dict[str, Any]:
    """면접 질문 생성 service 함수.

    Django View 또는 DRF APIView에서는 request.data를 그대로 넘겨 사용할 수 있다.

    Args:
        payload:
            {
                "user_id": "user_001",
                "resume_text": "...",
                "cover_letter_text": "...",
                "jd_text": "...",
                "career_type": "newcomer",
                "major_type": "major",
                "target_job": "backend_developer",
                "interview_depth": "light",
                "persona_id": "practical",
                "question_count": 3,
                "previous_questions": [],
                "missing_fields": ["result"]
            }

        mode:
            - "mock": API 키 없이 mock/rule 기반 생성
            - "llm": 실제 OpenAI API 호출

    Returns:
        QuestionGenerationResult를 dict로 변환한 값
    """

    try:
        request = QuestionGenerationRequest(
            user_id=payload["user_id"],
            resume_text=payload["resume_text"],
            cover_letter_text=payload.get("cover_letter_text"),
            jd_text=payload.get("jd_text"),
            career_type=payload["career_type"],
            major_type=payload["major_type"],
            target_job=payload["target_job"],
            interview_depth=payload.get("interview_depth", "light"),
            persona_id=payload.get("persona_id", "practical"),
            question_count=payload.get("question_count", 3),
            previous_questions=payload.get("previous_questions", []),
            missing_fields=payload.get("missing_fields", []),
        )

        result = generate_questions(request, mode=mode)
        return result.model_dump()

    except KeyError as exc:
        raise InterviewServiceError(f"질문 생성 필수 입력값이 누락되었습니다: {exc}") from exc

    except Exception as exc:
        raise InterviewServiceError(f"질문 생성 중 오류가 발생했습니다: {exc}") from exc


def create_follow_up_questions(
    payload: dict[str, Any],
    *,
    mode: RunMode = "mock",
) -> dict[str, Any]:
    """꼬리질문 생성 service 함수.

    Django View 또는 DRF APIView에서는 request.data를 그대로 넘겨 사용할 수 있다.

    Args:
        payload:
            {
                "question_id": "q_001",
                "question": "Django를 선택한 이유는 무엇인가요?",
                "answer": "팀원들이 Django를 써본 적이 있고...",
                "persona_id": "practical",
                "weaknesses": ["FastAPI와의 비교가 부족함"],
                "missing_keywords": ["대안 비교", "트레이드오프"],
                "weakness_tags": ["weak_technical_reasoning"],
                "max_follow_ups": 2
            }

        mode:
            - "mock": API 키 없이 mock/rule 기반 생성
            - "llm": 실제 OpenAI API 호출

    Returns:
        FollowUpGenerationResult를 dict로 변환한 값
    """

    try:
        request = FollowUpGenerationRequest(
            question_id=payload["question_id"],
            question=payload["question"],
            answer=payload["answer"],
            persona_id=payload.get("persona_id", "practical"),
            weaknesses=payload.get("weaknesses", []),
            missing_keywords=payload.get("missing_keywords", []),
            weakness_tags=payload.get("weakness_tags", []),
            max_follow_ups=payload.get("max_follow_ups", 2),
        )

        result = generate_follow_ups(request, mode=mode)
        return result.model_dump()

    except KeyError as exc:
        raise InterviewServiceError(f"꼬리질문 생성 필수 입력값이 누락되었습니다: {exc}") from exc

    except Exception as exc:
        raise InterviewServiceError(f"꼬리질문 생성 중 오류가 발생했습니다: {exc}") from exc


def run_single_turn_interview(
    payload: dict[str, Any],
    *,
    mode: RunMode = "mock",
) -> dict[str, Any]:
    """질문 생성 + 첫 번째 질문에 대한 꼬리질문 생성까지 한 번에 테스트하는 함수.

    MVP 개발 초기에 전체 흐름이 이어지는지 확인하기 위한 용도다.
    실제 서비스에서는 질문 생성 API와 꼬리질문 생성 API를 분리해서 쓰는 것이 좋다.
    """

    question_result = create_interview_questions(payload, mode=mode)

    questions = question_result.get("questions", [])
    if not questions:
        raise InterviewServiceError("생성된 질문이 없습니다.")

    first_question = questions[0]

    answer_text = payload.get(
        "answer",
        "팀원들이 해당 기술을 사용해본 경험이 있고 빠르게 구현할 수 있어서 선택했습니다.",
    )

    follow_up_payload = {
        "question_id": first_question["question_id"],
        "question": first_question["question"],
        "answer": answer_text,
        "persona_id": payload.get("persona_id", "practical"),
        "weaknesses": payload.get(
            "weaknesses",
            ["기술 선택 이유가 구체적이지 않음"],
        ),
        "missing_keywords": payload.get(
            "missing_keywords",
            ["대안 비교", "트레이드오프", "프로젝트 요구사항"],
        ),
        "weakness_tags": payload.get(
            "weakness_tags",
            ["weak_technical_reasoning", "lack_of_specificity"],
        ),
        "max_follow_ups": payload.get("max_follow_ups", 2),
    }

    follow_up_result = create_follow_up_questions(follow_up_payload, mode=mode)

    return {
        "session_id": question_result["session_id"],
        "user_id": question_result["user_id"],
        "persona_id": question_result["persona_id"],
        "questions": question_result["questions"],
        "first_turn": {
            "question": first_question,
            "answer": answer_text,
            "follow_ups": follow_up_result["follow_ups"],
        },
    }