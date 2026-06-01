from __future__ import annotations

from uuid import uuid4

from interview_ai.llm.openai_client import call_openai_chat
from interview_ai.prompts.followup_generation_prompt import (
    FOLLOWUP_GENERATION_SYSTEM_PROMPT,
    render_followup_generation_user_prompt,
)
from interview_ai.schemas.followup_schema import (
    FollowUpGenerationRequest,
    FollowUpGenerationResult,
    FollowUpQuestion,
)
from interview_ai.utils.json_parser import extract_json_object


def generate_follow_ups_mock(request: FollowUpGenerationRequest) -> FollowUpGenerationResult:
    """꼬리질문 생성 Chain A안 mock.

    실제 LLM 연동 전까지는 weakness_tags 또는 답변 길이 기반으로 생성한다.
    """

    follow_ups: list[FollowUpQuestion] = []

    if request.max_follow_ups == 0:
        return FollowUpGenerationResult(question_id=request.question_id, follow_ups=[])

    if "weak_technical_reasoning" in request.weakness_tags:
        follow_ups.append(
            FollowUpQuestion(
                follow_up_id=f"fu_{uuid4().hex[:8]}",
                question_id=request.question_id,
                follow_up_question="방금 답변에서 언급한 기술 선택을 다른 대안과 비교했을 때, 가장 중요한 판단 기준은 무엇이었나요?",
                follow_up_type="technical_reasoning",
                trigger_reason="기술 선택 이유는 언급했지만 대안 비교와 판단 기준이 부족함",
                based_on_weakness_tags=["weak_technical_reasoning"],
            )
        )

    if "missing_result" in request.weakness_tags and len(follow_ups) < request.max_follow_ups:
        follow_ups.append(
            FollowUpQuestion(
                follow_up_id=f"fu_{uuid4().hex[:8]}",
                question_id=request.question_id,
                follow_up_question="그 경험의 결과나 개선 효과를 수치 또는 구체적인 변화로 설명할 수 있나요?",
                follow_up_type="result_check",
                trigger_reason="성과나 결과 설명이 부족함",
                based_on_weakness_tags=["missing_result"],
            )
        )

    if not follow_ups and len(request.answer.strip()) < 50:
        follow_ups.append(
            FollowUpQuestion(
                follow_up_id=f"fu_{uuid4().hex[:8]}",
                question_id=request.question_id,
                follow_up_question="방금 답변을 조금 더 구체적으로 설명해주실 수 있나요?",
                follow_up_type="specificity_check",
                trigger_reason="답변 길이가 짧고 구체적인 근거가 부족함",
                based_on_weakness_tags=["lack_of_specificity"],
            )
        )

    return FollowUpGenerationResult(
        question_id=request.question_id,
        follow_ups=follow_ups[: request.max_follow_ups],
    )


def generate_follow_ups_llm(request: FollowUpGenerationRequest) -> FollowUpGenerationResult:
    """실제 LLM 기반 꼬리질문 생성."""

    raw_response = call_openai_chat(
        system_prompt=FOLLOWUP_GENERATION_SYSTEM_PROMPT,
        user_prompt=render_followup_generation_user_prompt(request),
        temperature=0.2,
    )

    parsed_json = extract_json_object(raw_response)
    parsed_json["question_id"] = request.question_id

    result = FollowUpGenerationResult.model_validate(parsed_json)
    return result


def generate_follow_ups(
    request: FollowUpGenerationRequest,
    *,
    mode: str = "mock",
) -> FollowUpGenerationResult:
    """꼬리질문 생성 public entrypoint.

    Args:
        request: 꼬리질문 생성 입력값
        mode:
            - "mock": API 키 없이 규칙 기반 mock 응답 생성
            - "llm": OpenAI API 호출
    """

    if mode == "mock":
        return generate_follow_ups_mock(request)
    if mode == "llm":
        return generate_follow_ups_llm(request)

    raise ValueError(f"지원하지 않는 mode입니다: {mode}")
