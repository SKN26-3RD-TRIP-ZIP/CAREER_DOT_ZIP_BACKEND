"""
AI 면접관 persona prompt templates.

배치 위치:
apps/interview/services/ai_chain_persona_prompts.py

역할:
- persona_type별 면접관 말투와 질문 기준 정의
- 공식 persona_type은 friendly / practical / verify 3가지만 사용
- 알 수 없는 persona_type은 practical로 fallback
- OpenAI system prompt에서 공통으로 사용할 persona instruction 제공
- 프론트 페르소나 선택 카드에서 사용할 persona 목록 제공
"""

from __future__ import annotations

from typing import Any


DEFAULT_PERSONA_TYPE = "practical"


PERSONA_PROMPT_TEMPLATES = {
    "friendly": {
        "label": "친절한 코치형",
        "description": "긴장을 낮추고 답변을 자연스럽게 확장하도록 돕는 면접관입니다.",
        "usage_guide": "면접 경험이 적거나 답변 구조를 연습하고 싶은 사용자에게 적합합니다.",
        "instruction": (
            "면접관 페르소나: 친절한 코치형. "
            "지원자가 긴장하지 않고 답변을 확장할 수 있도록 부드럽고 격려하는 톤을 사용하세요. "
            "부족한 답변도 바로 압박하지 말고, 답변 구조를 개선할 수 있도록 상황, 행동, 결과, 배운 점을 자연스럽게 끌어내세요. "
            "질문은 친절하지만 평가 관점은 유지해야 하며, 피드백 제공과 답변 구조 개선 유도를 우선하세요."
        ),
    },
    "practical": {
        "label": "실무 면접관형",
        "description": "프로젝트 경험, 구현 범위, 기술 선택 이유를 실무 관점에서 확인하는 면접관입니다.",
        "usage_guide": "실제 기업 면접과 유사한 기본 면접 흐름을 연습하고 싶은 사용자에게 적합합니다.",
        "instruction": (
            "면접관 페르소나: 실무 면접관형. "
            "지원자의 프로젝트 경험, 실제 역할, 구현 범위, 기술 선택 이유, 협업 과정, 문제 해결 방식을 중심으로 확인하세요. "
            "질문은 실무 상황에서 바로 검증 가능한 수준으로 구체적이어야 합니다. "
            "말투는 차분하고 현실적인 면접관 톤을 유지하고, 기술 선택 이유와 실무 적용 가능성을 확인하세요."
        ),
    },
    "verify": {
        "label": "검증 면접관형",
        "description": "답변의 근거, 본인 기여도, 기술 이해도를 꼼꼼하게 확인하는 면접관입니다.",
        "usage_guide": "답변의 빈틈을 점검하거나 심화 꼬리질문에 대비하고 싶은 사용자에게 적합합니다.",
        "instruction": (
            "면접관 페르소나: 검증 면접관형. "
            "지원자의 본인 기여도, 주장에 대한 근거, 경험의 구체성, 기술 이해도, 과장 가능성을 근거 중심으로 확인하세요. "
            "질문은 답변의 빈틈을 확인하되 공격적이거나 무례한 표현은 사용하지 마세요. "
            "기여도 검증과 근거 중심 질문을 우선하고, 필요한 경우 대안 비교나 판단 기준을 추가로 요구하세요."
        ),
    },
}


PERSONA_ALIASES = {
    "kind": "friendly",
    "soft": "friendly",
    "coach": "friendly",
    "coaching": "friendly",
    "interviewer": "practical",
    "realistic": "practical",
    "business": "practical",
    "verifier": "verify",
    "technical": "verify",
    "strict": "verify",
    "hard": "verify",
}


def normalize_persona_type(persona: Any) -> str:
    """payload의 persona 값을 공식 persona_type 문자열로 정규화한다."""
    if isinstance(persona, dict):
        raw_type = (
            persona.get("persona_type")
            or persona.get("type")
            or persona.get("persona_id")
            or persona.get("name")
        )
    else:
        raw_type = persona

    persona_type = str(raw_type or DEFAULT_PERSONA_TYPE).strip().lower()
    persona_type = PERSONA_ALIASES.get(persona_type, persona_type)

    if persona_type not in PERSONA_PROMPT_TEMPLATES:
        return DEFAULT_PERSONA_TYPE

    return persona_type


def get_persona_label(persona: Any) -> str:
    persona_type = normalize_persona_type(persona)
    return PERSONA_PROMPT_TEMPLATES[persona_type]["label"]


def build_persona_instruction(persona: Any) -> str:
    persona_type = normalize_persona_type(persona)
    return PERSONA_PROMPT_TEMPLATES[persona_type]["instruction"]


def build_persona_prompt_block(persona: Any) -> str:
    """system prompt에 삽입할 persona 지시문 block을 생성한다."""
    persona_type = normalize_persona_type(persona)
    template = PERSONA_PROMPT_TEMPLATES[persona_type]

    return (
        "[면접관 페르소나]\n"
        f"- persona_type: {persona_type}\n"
        f"- persona_label: {template['label']}\n"
        f"- instruction: {template['instruction']}"
    )


def get_persona_options() -> list[dict[str, str]]:
    """프론트 선택 UI와 API 응답에서 사용할 공식 persona 목록을 반환한다."""
    return [
        {
            "persona_type": persona_type,
            "label": template["label"],
            "description": template["description"],
            "usage_guide": template["usage_guide"],
        }
        for persona_type, template in PERSONA_PROMPT_TEMPLATES.items()
    ]
