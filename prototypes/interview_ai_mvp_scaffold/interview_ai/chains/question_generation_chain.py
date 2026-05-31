from __future__ import annotations

from uuid import uuid4

from interview_ai_mvp_scaffold.data.fallback_questions import FALLBACK_QUESTIONS
from interview_ai_mvp_scaffold.llm.openai_client import call_openai_chat
from interview_ai_mvp_scaffold.prompts.question_generation_prompt import (
    QUESTION_GENERATION_SYSTEM_PROMPT,
    render_question_generation_user_prompt,
)
from interview_ai_mvp_scaffold.schemas.question_schema import (
    InterviewQuestion,
    QuestionGenerationRequest,
    QuestionGenerationResult,
)
from interview_ai_mvp_scaffold.utils.json_parser import extract_json_object
from interview_ai_mvp_scaffold.validators.quality_rules import validate_question_quality


def generate_questions_mock(request: QuestionGenerationRequest) -> QuestionGenerationResult:
    """질문 생성 Chain A안 mock.

    실제 LLM 연동 전까지는 고정 규칙으로 질문을 생성한다.
    나중에 이 함수 내부만 LLM 호출로 교체하면 된다.
    """

    questions: list[InterviewQuestion] = []

    base_question = InterviewQuestion(
        question_id="q_001",
        question="프로젝트에서 사용한 핵심 기술을 선택한 이유와 다른 대안과 비교했을 때의 장단점은 무엇인가요?",
        question_type="technical_reasoning",
        source_type="resume_jd" if request.jd_text else "resume",
        source_summary="이력서/자소서에 작성된 프로젝트 기술 경험과 JD 요구 역량을 기반으로 생성한 질문",
        difficulty="medium",
        intent="기술 선택 이유와 트레이드오프 설명 능력을 확인하기 위한 질문",
        expected_keywords=["기술 선택 이유", "대안 비교", "트레이드오프", "프로젝트 요구사항"],
    )
    questions.append(base_question)

    if request.career_type == "newcomer":
        questions.append(
            InterviewQuestion(
                question_id="q_002",
                question="이 프로젝트를 진행하면서 새롭게 배운 점과 이후 비슷한 프로젝트를 한다면 보완하고 싶은 점은 무엇인가요?",
                question_type="growth_learning",
                source_type="cover_letter" if request.cover_letter_text else "resume",
                source_summary="신입 지원자의 학습 과정과 성장 가능성을 확인하기 위한 질문",
                difficulty="easy",
                intent="학습 태도와 회고 능력을 확인하기 위한 질문",
                expected_keywords=["배운 점", "회고", "개선점", "성장 가능성"],
            )
        )
    else:
        questions.append(
            InterviewQuestion(
                question_id="q_002",
                question="해당 경험에서 본인이 책임진 범위와 실제 성과를 실무 관점에서 설명해주실 수 있나요?",
                question_type="contribution_check",
                source_type="resume",
                source_summary="이직자의 책임 범위, 실무 성과, 재현 가능한 문제 해결력을 확인하기 위한 질문",
                difficulty="hard",
                intent="실무 기여도와 성과를 확인하기 위한 질문",
                expected_keywords=["책임 범위", "성과", "문제 해결", "재현 가능성"],
            )
        )

    if request.major_type == "major":
        questions.append(
            InterviewQuestion(
                question_id="q_003",
                question="구현 과정에서 고려한 구조적 설계나 성능상의 trade-off가 있었다면 설명해주실 수 있나요?",
                question_type="technical_reasoning",
                source_type="resume",
                source_summary="전공자의 CS 기본기와 구조적 이해를 확인하기 위한 질문",
                difficulty="hard" if request.interview_depth != "light" else "medium",
                intent="구조적 이해와 기술적 판단 기준을 확인하기 위한 질문",
                expected_keywords=["구조", "성능", "trade-off", "설계 판단"],
            )
        )
    else:
        questions.append(
            InterviewQuestion(
                question_id="q_003",
                question="비전공자로서 해당 기술을 학습하고 프로젝트에 적용하는 과정에서 가장 어려웠던 부분은 무엇이었나요?",
                question_type="growth_learning",
                source_type="cover_letter" if request.cover_letter_text else "resume",
                source_summary="비전공자의 학습 과정, 적용 경험, 설명력을 확인하기 위한 질문",
                difficulty="medium",
                intent="학습 과정과 실제 적용 경험을 확인하기 위한 질문",
                expected_keywords=["학습 과정", "어려움", "적용 경험", "보완"],
            )
        )

    for missing_field in request.missing_fields:
        fallback = FALLBACK_QUESTIONS.get(missing_field)
        if not fallback:
            continue

        questions.append(
            InterviewQuestion(
                question_id=f"q_fb_{missing_field}",
                question=fallback,
                question_type="fallback",
                source_type="fallback",
                source_summary=f"입력 자료에서 {missing_field} 정보가 부족하여 생성한 보완 질문",
                difficulty="easy",
                intent="입력 자료에서 누락된 핵심 정보를 보완하기 위한 질문",
                expected_keywords=[missing_field],
            )
        )

    selected_questions = questions[: request.question_count]
    _validate_questions(selected_questions, request.previous_questions)

    return QuestionGenerationResult(
        session_id=f"session_{uuid4().hex[:8]}",
        user_id=request.user_id,
        persona_id=request.persona_id,
        questions=selected_questions,
    )


def generate_questions_llm(request: QuestionGenerationRequest) -> QuestionGenerationResult:
    """실제 LLM 기반 질문 생성.

    흐름:
    1. prompt 생성
    2. OpenAI 호출
    3. JSON 추출
    4. Pydantic 검증
    5. rule-based 품질 검증
    """

    raw_response = call_openai_chat(
        system_prompt=QUESTION_GENERATION_SYSTEM_PROMPT,
        user_prompt=render_question_generation_user_prompt(request),
        temperature=0.2,
    )

    parsed_json = extract_json_object(raw_response)

    # LLM이 session_id를 임시값으로 주는 경우를 대비해 보정
    parsed_json.setdefault("session_id", f"session_{uuid4().hex[:8]}")
    parsed_json["user_id"] = request.user_id
    parsed_json["persona_id"] = request.persona_id

    result = QuestionGenerationResult.model_validate(parsed_json)
    _validate_questions(result.questions, request.previous_questions)

    return result


def generate_questions(
    request: QuestionGenerationRequest,
    *,
    mode: str = "mock",
) -> QuestionGenerationResult:
    """질문 생성 public entrypoint.

    Args:
        request: 질문 생성 입력값
        mode:
            - "mock": API 키 없이 규칙 기반 mock 응답 생성
            - "llm": OpenAI API 호출
    """

    if mode == "mock":
        return generate_questions_mock(request)
    if mode == "llm":
        return generate_questions_llm(request)

    raise ValueError(f"지원하지 않는 mode입니다: {mode}")


def _validate_questions(
    questions: list[InterviewQuestion],
    previous_questions: list[str],
) -> None:
    for question in questions:
        quality_errors = validate_question_quality(question, previous_questions)
        if quality_errors:
            raise ValueError(
                f"question quality check failed: {question.question_id} / {quality_errors}"
            )
