"""
AI 면접 Chain 공통 계약값.

배치 위치:
backend/apps/interview/ai_chain_contracts.py

역할:
- AI Chain / API / FE가 공통으로 맞춰야 하는 enum 값 관리
- mock 개발 단계에서 사용할 기본 페르소나, 약점 태그 후보 제공
"""

from enum import Enum
from typing import Any


class PersonaType(str, Enum):
    COACH = "coach"
    PRACTICAL = "practical"
    VERIFY = "verify"


class QuestionType(str, Enum):
    TECHNICAL = "technical"
    PERSONALITY = "personality"
    JOB = "job"
    GENERAL = "general"


class SourceType(str, Enum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    JD = "jd"
    QUESTION_BANK = "question_bank"
    PROJECT_EXPERIENCE = "project_experience"


class NextAction(str, Enum):
    GENERATE_FOLLOWUP = "GENERATE_FOLLOWUP"
    NEXT_QUESTION = "NEXT_QUESTION"


DEFAULT_PERSONAS: list[dict[str, Any]] = [
    {
        "persona_id": 1,
        "persona_type": PersonaType.COACH.value,
        "name": "친절한 코치형",
        "description": "지원자의 답변을 부드럽게 보완하도록 돕는 면접관",
    },
    {
        "persona_id": 2,
        "persona_type": PersonaType.PRACTICAL.value,
        "name": "실무 면접관형",
        "description": "프로젝트 경험, 기술 선택 이유, 문제 해결 과정을 중심으로 확인하는 면접관",
    },
    {
        "persona_id": 3,
        "persona_type": PersonaType.VERIFY.value,
        "name": "검증 면접관형",
        "description": "답변의 사실성, 본인 기여도, 근거를 날카롭게 확인하는 면접관",
    },
]


DEFAULT_WEAKNESS_TAG_CANDIDATES: list[dict[str, Any]] = [
    {
        "weakness_tag_id": "00000000-0000-0000-0000-000000000001",
        "tag_name": "답변 구체성 부족",
        "description": "답변에 구체적인 상황, 행동, 결과가 부족한 경우",
    },
    {
        "weakness_tag_id": "00000000-0000-0000-0000-000000000002",
        "tag_name": "본인 기여도 불명확",
        "description": "프로젝트에서 본인이 맡은 역할과 기여가 명확하지 않은 경우",
    },
    {
        "weakness_tag_id": "00000000-0000-0000-0000-000000000003",
        "tag_name": "기술 선택 이유 부족",
        "description": "사용한 기술이나 도구를 선택한 이유가 부족한 경우",
    },
    {
        "weakness_tag_id": "00000000-0000-0000-0000-000000000004",
        "tag_name": "직무 연관성 부족",
        "description": "답변 내용이 지원 직무나 JD 요구 역량과 충분히 연결되지 않은 경우",
    },
]
