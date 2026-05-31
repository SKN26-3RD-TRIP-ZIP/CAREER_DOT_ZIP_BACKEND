from __future__ import annotations

import json

from interview_ai_mvp_scaffold.data.personas import PERSONAS
from interview_ai_mvp_scaffold.schemas.question_schema import QuestionGenerationRequest


QUESTION_GENERATION_SYSTEM_PROMPT = """당신은 IT 직무 면접 질문을 생성하는 AI 면접관입니다.

목표:
- 사용자의 이력서, 자기소개서, JD를 기반으로 실제 면접에서 물어볼 만한 질문을 생성합니다.
- 질문은 너무 일반적이면 안 됩니다.
- 질문마다 근거 문서와 질문 의도를 함께 제공합니다.
- 출력은 반드시 JSON object만 반환합니다.
- 마크다운 코드블록, 설명 문장, 주석을 출력하지 마세요.

반영해야 할 조건:
- career_type이 newcomer이면 학습 과정, 프로젝트 이해도, 성장 가능성을 더 확인합니다.
- career_type이 experienced이면 책임 범위, 성과, 실무 문제 해결력을 더 확인합니다.
- major_type이 major이면 CS 기본기, 구조적 이해, trade-off를 더 확인합니다.
- major_type이 non_major이면 학습 과정, 적용 경험, 설명력을 더 확인합니다.
- persona_id에 따라 질문 톤과 초점을 조정합니다.

허용 question_type:
- project_experience
- technical_reasoning
- contribution_check
- problem_solving
- job_fit
- collaboration
- growth_learning
- fallback

허용 source_type:
- resume
- cover_letter
- jd
- resume_jd
- user_setting
- fallback

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
"""


def render_question_generation_user_prompt(request: QuestionGenerationRequest) -> str:
    persona = PERSONAS.get(request.persona_id, {})

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
        "question_count": request.question_count,
        "previous_questions": request.previous_questions,
        "missing_fields": request.missing_fields,
        "documents": {
            "resume_text": request.resume_text,
            "cover_letter_text": request.cover_letter_text,
            "jd_text": request.jd_text,
        },
    }

    return (
        "아래 입력값을 기반으로 면접 질문을 생성하세요. "
        "반드시 지정된 JSON object만 반환하세요.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
