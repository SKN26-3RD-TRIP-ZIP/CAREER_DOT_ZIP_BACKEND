"""AI 면접관 파트 공통 분류 기준.

용도:
- 질문 생성, 답변 평가, 꼬리질문 생성, 최종 리포트에서 공통으로 사용하는 태그/유형 정의
- FE/BE/평가/리포트 담당자와 필드명을 맞추기 위한 기준 파일

주의:
- schema의 Literal 값과 반드시 동일하게 유지해야 한다.
- 값 변경 시 question_schema.py, followup_schema.py, evaluation_schema.py도 함께 확인한다.
"""

from __future__ import annotations


QUESTION_TYPES: dict[str, dict[str, str]] = {
    "project_experience": {
        "label": "프로젝트 경험",
        "description": "프로젝트의 전체 맥락, 목표, 진행 과정, 본인 경험을 확인하는 질문",
        "example": "해당 프로젝트를 진행하게 된 배경과 본인이 맡은 역할을 설명해 주세요.",
    },
    "technical_reasoning": {
        "label": "기술 선택/이해",
        "description": "기술 선택 이유, 대안 비교, 트레이드오프, 기술 원리를 확인하는 질문",
        "example": "Django를 선택한 이유와 FastAPI와 비교했을 때의 장단점을 설명해 주세요.",
    },
    "contribution_check": {
        "label": "본인 기여도",
        "description": "팀 프로젝트에서 본인이 직접 수행한 역할과 기여 범위를 확인하는 질문",
        "example": "이 기능 구현에서 본인이 직접 담당한 부분은 어디까지였나요?",
    },
    "problem_solving": {
        "label": "문제 해결",
        "description": "문제 상황, 원인 분석, 해결 과정, 결과를 확인하는 질문",
        "example": "프로젝트 중 가장 어려웠던 문제와 이를 해결한 과정을 설명해 주세요.",
    },
    "job_fit": {
        "label": "직무 적합성",
        "description": "JD 요구사항과 사용자 경험이 얼마나 연결되는지 확인하는 질문",
        "example": "JD에서 요구하는 SQL 역량과 관련해 수행한 경험을 설명해 주세요.",
    },
    "collaboration": {
        "label": "협업/커뮤니케이션",
        "description": "팀 협업, 역할 분담, 소통 방식, 갈등 해결 경험을 확인하는 질문",
        "example": "프론트엔드 팀원과 API 명세를 맞추는 과정에서 어떻게 소통했나요?",
    },
    "growth_learning": {
        "label": "학습/성장",
        "description": "학습 과정, 회고, 개선점, 성장 가능성을 확인하는 질문",
        "example": "이 프로젝트를 통해 배운 점과 다음에 보완하고 싶은 점은 무엇인가요?",
    },
    "fallback": {
        "label": "보완 질문",
        "description": "입력 자료에서 핵심 정보가 부족할 때 생성하는 보완 질문",
        "example": "프로젝트 결과나 개선 효과를 구체적으로 설명해 주실 수 있나요?",
    },
}


FOLLOW_UP_TYPES: dict[str, dict[str, str]] = {
    "specificity_check": {
        "label": "구체성 확인",
        "description": "답변이 추상적일 때 구체적인 사례, 근거, 상황을 확인하는 꼬리질문",
        "example": "방금 말씀하신 문제 상황을 조금 더 구체적인 사례로 설명해 주실 수 있나요?",
    },
    "technical_reasoning": {
        "label": "기술 근거 확인",
        "description": "기술 선택 이유, 대안 비교, 트레이드오프 설명을 확인하는 꼬리질문",
        "example": "FastAPI와 비교했을 때 Django를 선택한 기준은 무엇이었나요?",
    },
    "contribution_check": {
        "label": "기여도 확인",
        "description": "본인이 직접 수행한 작업 범위와 책임을 확인하는 꼬리질문",
        "example": "그 과정에서 본인이 직접 구현한 부분은 어디까지였나요?",
    },
    "result_check": {
        "label": "성과 확인",
        "description": "결과, 개선 효과, 정량 지표, 피드백을 확인하는 꼬리질문",
        "example": "그 개선 결과를 수치나 사용자 피드백으로 설명할 수 있나요?",
    },
    "job_fit_check": {
        "label": "직무 연결 확인",
        "description": "답변을 지원 직무/JD 요구사항과 연결하는 꼬리질문",
        "example": "이 경험이 지원한 백엔드 개발자 직무와 어떻게 연결된다고 생각하나요?",
    },
    "problem_solving_deepening": {
        "label": "문제 해결 심화",
        "description": "문제 원인 분석, 해결 과정, 선택 기준을 더 깊게 확인하는 꼬리질문",
        "example": "그 문제의 원인을 어떻게 파악했고, 왜 그 해결 방식을 선택했나요?",
    },
    "answer_structure": {
        "label": "답변 구조 보완",
        "description": "답변 흐름이 정리되지 않았을 때 구조화된 답변을 유도하는 꼬리질문",
        "example": "상황, 역할, 행동, 결과 순서로 다시 정리해서 설명해 주실 수 있나요?",
    },
}


WEAKNESS_TAGS: dict[str, dict[str, str]] = {
    "lack_of_specificity": {
        "label": "구체성 부족",
        "description": "상황, 역할, 행동, 결과가 구체적으로 드러나지 않음",
        "recommended_follow_up_type": "specificity_check",
        "report_usage": "답변에 구체적인 사례와 근거를 추가하도록 안내",
    },
    "weak_technical_reasoning": {
        "label": "기술적 근거 부족",
        "description": "기술 선택 이유, 대안 비교, 트레이드오프 설명이 부족함",
        "recommended_follow_up_type": "technical_reasoning",
        "report_usage": "기술 선택 기준과 비교 대안을 설명하도록 안내",
    },
    "unclear_contribution": {
        "label": "본인 기여도 불명확",
        "description": "팀 프로젝트에서 본인이 직접 수행한 역할이 명확하지 않음",
        "recommended_follow_up_type": "contribution_check",
        "report_usage": "본인이 직접 맡은 작업과 책임 범위를 구체화하도록 안내",
    },
    "missing_result": {
        "label": "성과 설명 부족",
        "description": "프로젝트 결과나 개선 효과가 구체적으로 제시되지 않음",
        "recommended_follow_up_type": "result_check",
        "report_usage": "정량 지표, 결과, 피드백을 포함하도록 안내",
    },
    "weak_job_fit": {
        "label": "직무 연관성 부족",
        "description": "답변이 지원 직무의 요구 역량과 충분히 연결되지 않음",
        "recommended_follow_up_type": "job_fit_check",
        "report_usage": "경험과 JD 요구사항의 연결성을 보완하도록 안내",
    },
    "shallow_problem_solving": {
        "label": "문제 해결 과정 부족",
        "description": "문제 상황, 원인 분석, 해결 과정이 얕게 설명됨",
        "recommended_follow_up_type": "problem_solving_deepening",
        "report_usage": "문제 원인, 해결 과정, 선택 이유를 단계적으로 설명하도록 안내",
    },
    "missing_keywords": {
        "label": "핵심 키워드 누락",
        "description": "질문 의도상 포함되어야 할 핵심 개념이나 용어가 빠짐",
        "recommended_follow_up_type": "specificity_check",
        "report_usage": "누락된 핵심 키워드를 보완하도록 안내",
    },
    "unstructured_answer": {
        "label": "답변 구조 부족",
        "description": "답변 흐름이 정리되어 있지 않아 핵심이 잘 전달되지 않음",
        "recommended_follow_up_type": "answer_structure",
        "report_usage": "STAR 구조 등으로 답변을 재구성하도록 안내",
    },
}


WEAKNESS_TO_FOLLOW_UP_TYPE: dict[str, str] = {
    tag: meta["recommended_follow_up_type"]
    for tag, meta in WEAKNESS_TAGS.items()
}


def get_question_type_label(question_type: str) -> str:
    return QUESTION_TYPES.get(question_type, {}).get("label", question_type)


def get_follow_up_type_label(follow_up_type: str) -> str:
    return FOLLOW_UP_TYPES.get(follow_up_type, {}).get("label", follow_up_type)


def get_weakness_tag_label(weakness_tag: str) -> str:
    return WEAKNESS_TAGS.get(weakness_tag, {}).get("label", weakness_tag)
