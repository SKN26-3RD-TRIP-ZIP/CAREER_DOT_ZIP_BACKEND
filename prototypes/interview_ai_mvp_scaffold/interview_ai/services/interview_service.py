from __future__ import annotations

from typing import Any, Literal

from interview_ai.chains.followup_generation_chain import generate_follow_ups
from interview_ai.chains.question_generation_chain import generate_questions
from interview_ai.schemas.evaluation_schema import AnswerEvaluationResult
from interview_ai.schemas.followup_schema import FollowUpGenerationRequest
from interview_ai.schemas.question_schema import QuestionGenerationRequest


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


def create_follow_up_questions_from_evaluation(
    payload: dict[str, Any],
    *,
    mode: RunMode = "mock",
) -> dict[str, Any]:
    """평가 결과 기반 꼬리질문 생성 service 함수.

    평가 담당 파트에서 생성한 evaluation_result를 받아서
    weaknesses, missing_keywords, weakness_tags를 꼬리질문 생성 Chain에 연결한다.

    Args:
        payload:
            {
                "question_id": "q_001",
                "question": "Django를 선택한 이유는 무엇인가요?",
                "answer": "팀원들이 Django를 써본 적이 있고...",
                "persona_id": "practical",
                "evaluation_result": {
                    "evaluation_id": "eval_001",
                    "question_id": "q_001",
                    "answer": "팀원들이 Django를 써본 적이 있고...",
                    "score": 3,
                    "strengths": [...],
                    "weaknesses": [...],
                    "missing_keywords": [...],
                    "weakness_tags": [...]
                },
                "max_follow_ups": 2
            }

        mode:
            - "mock": API 키 없이 mock/rule 기반 생성
            - "llm": 실제 OpenAI API 호출

    Returns:
        FollowUpGenerationResult를 dict로 변환한 값
    """

    try:
        evaluation_payload = payload["evaluation_result"]
        evaluation = AnswerEvaluationResult.model_validate(evaluation_payload)

        request = FollowUpGenerationRequest(
            question_id=payload.get("question_id", evaluation.question_id),
            question=payload["question"],
            answer=payload.get("answer", evaluation.answer),
            persona_id=payload.get("persona_id", "practical"),
            weaknesses=evaluation.weaknesses,
            missing_keywords=evaluation.missing_keywords,
            weakness_tags=evaluation.weakness_tags,
            max_follow_ups=payload.get("max_follow_ups", 2),
        )

        result = generate_follow_ups(request, mode=mode)

        return {
            **result.model_dump(),
            "evaluation_link": {
                "evaluation_id": evaluation.evaluation_id,
                "score": evaluation.score,
                "weakness_tags": evaluation.weakness_tags,
                "missing_keywords": evaluation.missing_keywords,
            },
        }

    except KeyError as exc:
        raise InterviewServiceError(
            f"평가 결과 기반 꼬리질문 생성 필수 입력값이 누락되었습니다: {exc}"
        ) from exc

    except Exception as exc:
        raise InterviewServiceError(
            f"평가 결과 기반 꼬리질문 생성 중 오류가 발생했습니다: {exc}"
        ) from exc


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


def run_single_turn_interview_with_evaluation(
    payload: dict[str, Any],
    *,
    mode: RunMode = "mock",
) -> dict[str, Any]:
    """질문 생성 + 평가 결과 기반 꼬리질문 생성까지 테스트하는 함수.

    평가 Chain이 실제로 붙기 전까지는 payload의 evaluation_result mock을 사용한다.
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

    evaluation_result = payload.get(
        "evaluation_result",
        {
            "evaluation_id": "eval_mock_001",
            "question_id": first_question["question_id"],
            "answer": answer_text,
            "score": 3,
            "strengths": [
                "프로젝트 경험을 언급함",
            ],
            "weaknesses": [
                "기술 선택 이유가 구체적이지 않음",
                "대안 비교와 트레이드오프 설명이 부족함",
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
    )

    follow_up_result = create_follow_up_questions_from_evaluation(
        {
            "question_id": first_question["question_id"],
            "question": first_question["question"],
            "answer": answer_text,
            "persona_id": payload.get("persona_id", "practical"),
            "evaluation_result": evaluation_result,
            "max_follow_ups": payload.get("max_follow_ups", 2),
        },
        mode=mode,
    )

    return {
        "session_id": question_result["session_id"],
        "user_id": question_result["user_id"],
        "persona_id": question_result["persona_id"],
        "questions": question_result["questions"],
        "first_turn": {
            "question": first_question,
            "answer": answer_text,
            "evaluation_result": evaluation_result,
            "follow_ups": follow_up_result["follow_ups"],
            "evaluation_link": follow_up_result["evaluation_link"],
        },
    }
