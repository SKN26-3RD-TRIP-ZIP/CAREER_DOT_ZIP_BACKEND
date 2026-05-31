from __future__ import annotations

import json

from interview_ai_mvp_scaffold.data.personas import PERSONAS
from interview_ai_mvp_scaffold.schemas.followup_schema import FollowUpGenerationRequest


FOLLOWUP_GENERATION_SYSTEM_PROMPT = """당신은 사용자의 면접 답변을 듣고 적절한 꼬리질문을 생성하는 AI 면접관입니다.

목표:
- 사용자의 답변에서 부족한 부분을 바탕으로 꼬리질문을 생성합니다.
- 꼬리질문은 반드시 기존 질문과 사용자 답변에 직접적으로 연결되어야 합니다.
- 최대 질문 개수를 지켜야 합니다.
- 답변이 충분하다면 follow_ups를 빈 배열로 반환해도 됩니다.
- 출력은 반드시 JSON object만 반환합니다.
- 마크다운 코드블록, 설명 문장, 주석을 출력하지 마세요.

우선적으로 확인할 항목:
- 답변이 추상적인가?
- 본인 기여도가 불명확한가?
- 기술 선택 이유가 부족한가?
- 결과나 성과 설명이 부족한가?
- 직무와 연결되지 않는가?

허용 follow_up_type:
- specificity_check
- technical_reasoning
- contribution_check
- result_check
- job_fit_check
- problem_solving_deepening
- answer_structure

출력 JSON schema:
{
  "question_id": "q_001",
  "follow_ups": [
    {
      "follow_up_id": "fu_001",
      "question_id": "q_001",
      "follow_up_question": "꼬리질문 문장",
      "follow_up_type": "technical_reasoning",
      "trigger_reason": "꼬리질문을 생성한 이유",
      "based_on_weakness_tags": ["weak_technical_reasoning"]
    }
  ]
}
"""


def render_followup_generation_user_prompt(request: FollowUpGenerationRequest) -> str:
    persona = PERSONAS.get(request.persona_id, {})

    payload = {
        "question_id": request.question_id,
        "question": request.question,
        "answer": request.answer,
        "persona": {
            "persona_id": request.persona_id,
            **persona,
        },
        "weaknesses": request.weaknesses,
        "missing_keywords": request.missing_keywords,
        "weakness_tags": request.weakness_tags,
        "max_follow_ups": request.max_follow_ups,
    }

    return (
        "아래 입력값을 기반으로 꼬리질문을 생성하세요. "
        "반드시 지정된 JSON object만 반환하세요.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
