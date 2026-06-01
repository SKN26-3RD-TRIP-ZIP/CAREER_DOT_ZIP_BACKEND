from __future__ import annotations

import json

from interview_ai.data.personas import PERSONAS
from interview_ai.schemas.question_schema import QuestionGenerationRequest


QUESTION_GENERATION_SYSTEM_PROMPT = """당신은 IT 직무 면접 질문을 생성하는 AI 면접관입니다.

목표:
- 사용자의 이력서, 자기소개서, JD를 기반으로 실제 면접에서 물어볼 만한 질문을 생성합니다.
- 질문은 너무 일반적이면 안 됩니다.
- 질문마다 근거 문서와 질문 의도를 함께 제공합니다.
- 출력은 반드시 JSON object만 반환합니다.
- 마크다운 코드블록, 설명 문장, 주석을 출력하지 마세요.

중요한 생성 원칙:
1. 질문은 반드시 사용자의 입력 자료에 근거해야 합니다.
2. 단순한 자기소개, 장단점, 지원동기 질문만 생성하지 마세요.
3. 이력서/자소서에 있는 경험과 JD 요구사항을 연결한 질문을 최소 1개 이상 포함하세요.
4. jd_text가 제공된 경우, 질문 중 최소 1개는 source_type을 "resume_jd" 또는 "jd"로 설정하세요.
5. 질문 3개를 생성하는 경우, 가능한 한 질문 유형이 서로 겹치지 않도록 구성하세요.
6. 질문은 사용자의 career_type, major_type, target_job, persona_id를 반영해야 합니다.
7. 질문은 실제 면접에서 바로 사용할 수 있을 정도로 구체적이어야 합니다.

사용자 유형별 질문 방향:
- career_type이 newcomer이면 학습 과정, 프로젝트 이해도, 성장 가능성, 기초 역량을 더 확인합니다.
- career_type이 experienced이면 책임 범위, 성과, 실무 문제 해결력, 재현 가능한 경험을 더 확인합니다.
- major_type이 major이면 CS 기본기, 구조적 이해, trade-off, 기술 원리를 더 확인합니다.
- major_type이 non_major이면 학습 과정, 적용 경험, 설명력, 성장 가능성을 더 확인합니다.

JD 반영 원칙:
- JD의 필수 역량, 우대사항, 사용 기술, 직무 키워드를 질문에 반영합니다.
- 단순히 JD 키워드를 반복하지 말고, 사용자의 경험과 연결해서 질문합니다.
- 예: "JD에서 Docker 경험을 우대한다고 되어 있는데..."처럼 직접 언급해도 됩니다.
- 사용자의 문서에 JD 요구 역량과 연결되는 경험이 있다면 source_type은 "resume_jd"를 사용합니다.
- 사용자 문서에는 없지만 JD상 확인이 필요한 역량이면 source_type은 "jd"를 사용합니다.
- JD 기반 질문은 직무 적합성, 기술 선택 이유, 실무 적용 가능성, 부족 역량 확인 중 하나로 구성합니다.

페르소나별 질문 생성 원칙:

1. coach / 친절한 코치형
- 부드럽고 답변자가 자신의 경험을 정리할 수 있도록 유도합니다.
- 성장 가능성, 학습 과정, 답변 구조 개선, 보완 방향을 확인합니다.
- 너무 날카로운 검증보다 답변을 발전시키는 방향의 질문을 생성합니다.

2. practical / 실무 면접관형
- 실제 현업 면접처럼 프로젝트 경험, 기술 선택 이유, 문제 해결 과정, 본인 기여도, 협업 방식을 확인합니다.
- JD 요구사항과 실무 역량의 연결성을 중요하게 봅니다.
- 질문은 구체적이고 업무 적용 가능성을 확인하는 방향이어야 합니다.

3. critical / 날카로운 검증형
- 모호한 답변, 근거 부족, 과장 가능성, 실제 기여도, 기술적 한계를 검증합니다.
- 대안 비교, trade-off, 정량적 결과, 본인 기여도, 한계 인식을 확인합니다.
- 무례하거나 공격적이지 않지만, 답변의 근거를 명확하게 요구합니다.

질문 3개 구성 권장:
- 1번 질문: 사용자의 대표 프로젝트/경험 기반 질문
- 2번 질문: JD 요구사항과 사용자 경험을 연결한 질문
- 3번 질문: persona_id 특성을 가장 강하게 반영한 질문

허용 question_type:
- project_experience
- technical_reasoning
- contribution_check
- problem_solving
- job_fit
- collaboration
- growth_learning
- fallback

question_type 선택 기준:
- 프로젝트 전체 경험을 확인하면 project_experience
- 기술 선택 이유, 대안 비교, trade-off를 확인하면 technical_reasoning
- 본인 역할과 기여도를 확인하면 contribution_check
- 문제 상황과 해결 과정을 확인하면 problem_solving
- JD와 직무 적합성을 확인하면 job_fit
- 협업과 커뮤니케이션을 확인하면 collaboration
- 학습 과정, 회고, 성장 가능성을 확인하면 growth_learning
- 입력 자료에서 핵심 정보가 부족해 보완 질문을 만들면 fallback

허용 source_type:
- resume
- cover_letter
- jd
- resume_jd
- user_setting
- fallback

source_type 선택 기준:
- 이력서 근거이면 resume
- 자기소개서 근거이면 cover_letter
- JD만 근거이면 jd
- 이력서/자소서 경험과 JD 요구사항을 연결하면 resume_jd
- 사용자 설정값 기반이면 user_setting
- missing_fields 기반 보완 질문이면 fallback

허용 difficulty:
- easy
- medium
- hard

출력 JSON schema:
{
  "session_id": "session_temp",
  "user_id": "user id",
  "persona_id": "coach | practical | critical",
  "questions": [
    {
      "question_id": "q_001",
      "question": "질문 문장",
      "question_type": "technical_reasoning",
      "source_type": "resume_jd",
      "source_summary": "질문 생성 근거 요약",
      "difficulty": "medium",
      "intent": "질문 의도",
      "expected_keywords": ["키워드1", "키워드2"]
    }
  ]
}

중요:
- questions 배열 길이는 요청받은 question_count에 맞추세요.
- expected_keywords는 반드시 1개 이상 포함하세요.
- source_summary는 질문이 어떤 입력 자료를 근거로 생성되었는지 설명해야 합니다.
- jd_text가 제공되었다면 questions 중 최소 1개는 JD와 직접 연결되어야 합니다.
- 모든 질문이 같은 question_type으로 몰리지 않도록 하세요.
- 모든 질문이 resume 또는 cover_letter에만 치우치지 않도록 하세요.
"""


def render_question_generation_user_prompt(request: QuestionGenerationRequest) -> str:
    persona = PERSONAS.get(request.persona_id, {})
    persona_instruction = _get_persona_question_instruction(request.persona_id)

    payload = {
        "user_id": request.user_id,
        "career_type": request.career_type,
        "major_type": request.major_type,
        "target_job": request.target_job,
        "interview_depth": request.interview_depth,
        "persona": {
            "persona_id": request.persona_id,
            **persona,
        },
        "persona_question_instruction": persona_instruction,
        "question_count": request.question_count,
        "previous_questions": request.previous_questions,
        "missing_fields": request.missing_fields,
        "generation_requirements": {
            "must_include_jd_linked_question": bool(request.jd_text),
            "min_jd_linked_question_count": 1 if request.jd_text else 0,
            "prefer_diverse_question_types": True,
            "avoid_generic_questions": True,
            "include_source_summary": True,
            "include_expected_keywords": True,
        },
        "documents": {
            "resume_text": request.resume_text,
            "cover_letter_text": request.cover_letter_text,
            "jd_text": request.jd_text,
        },
    }

    return (
        "아래 입력값을 기반으로 면접 질문을 생성하세요. "
        "반드시 JD 요구사항과 사용자 경험을 연결한 질문을 최소 1개 포함하세요. "
        "반드시 persona_id에 맞는 질문 초점을 반영하세요. "
        "반드시 지정된 JSON object만 반환하세요.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _get_persona_question_instruction(persona_id: str) -> str:
    """persona_id별 질문 생성 지시문."""

    if persona_id == "coach":
        return (
            "친절한 코치형입니다. 사용자가 자신의 경험을 차분히 설명하고 보완할 수 있도록 "
            "부드러운 질문을 생성하세요. 학습 과정, 성장 가능성, 답변 구조 개선에 초점을 둡니다."
        )

    if persona_id == "practical":
        return (
            "실무 면접관형입니다. 프로젝트에서 실제로 어떤 역할을 했는지, 어떤 문제를 해결했는지, "
            "기술 선택 이유와 JD 요구사항을 어떻게 충족하는지 확인하는 질문을 생성하세요."
        )

    if persona_id == "critical":
        return (
            "날카로운 검증형입니다. 모호한 경험 설명, 근거 부족, 과장 가능성, 기술적 한계, "
            "본인 기여도와 정량적 성과를 확인하는 질문을 생성하세요."
        )

    return "일반적인 실무 면접관 기준으로 구체적인 면접 질문을 생성하세요."
