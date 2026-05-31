from __future__ import annotations

from typing import Any


MOCK_USERS: list[dict[str, Any]] = [
    {
        "user_id": "user_001",
        "name": "신입 전공자 백엔드 지원자",
        "career_type": "newcomer",
        "major_type": "major",
        "target_job": "backend_developer",
        "interview_depth": "light",
        "persona_id": "practical",
    },
    {
        "user_id": "user_002",
        "name": "신입 비전공자 데이터 분석가 지원자",
        "career_type": "newcomer",
        "major_type": "non_major",
        "target_job": "data_analyst",
        "interview_depth": "light",
        "persona_id": "coach",
    },
    {
        "user_id": "user_003",
        "name": "이직 전공자 AI 엔지니어 지원자",
        "career_type": "experienced",
        "major_type": "major",
        "target_job": "ai_engineer",
        "interview_depth": "real",
        "persona_id": "critical",
    },
]


MOCK_DOCUMENTS: dict[str, dict[str, Any]] = {
    "user_001": {
        "document_id": "doc_001",
        "resume_text": (
            "컴퓨터공학 전공. Django REST Framework 기반 팀 프로젝트에서 백엔드 API 구현을 담당했습니다. "
            "회원 인증, 게시글 CRUD, 댓글 기능, Swagger 문서화를 구현했으며 SQLite를 사용했습니다. "
            "팀 프로젝트에서 GitHub Flow를 사용했고, API 명세를 프론트엔드 팀원과 공유했습니다."
        ),
        "cover_letter_text": (
            "백엔드 개발자로서 안정적인 API 설계와 협업을 중요하게 생각합니다. "
            "프로젝트 진행 중 프론트엔드와 API 응답 형식을 맞추는 과정에서 소통의 중요성을 배웠습니다. "
            "Django를 선택한 이유는 빠른 개발과 인증 기능 구현이 수월했기 때문입니다."
        ),
        "jd_text": (
            "주니어 백엔드 개발자 채용. Python/Django 기반 API 개발 경험, REST API 이해, "
            "RDBMS 사용 경험, Git 협업 경험을 요구합니다. 우대사항으로 Docker 경험과 테스트 코드 작성 경험이 있습니다."
        ),
        "missing_fields": ["result"],
    },
    "user_002": {
        "document_id": "doc_002",
        "resume_text": (
            "비전공자로 데이터 분석 부트캠프를 수강하며 Python, SQL, 머신러닝 프로젝트를 수행했습니다. "
            "음악 구독 서비스 이탈 예측 프로젝트에서 RFM 유사 피처를 설계하고 KMeans 군집화를 진행했습니다. "
            "CatBoost, XGBoost, LightGBM 모델을 비교했고 AUC 기준으로 모델 성능을 평가했습니다."
        ),
        "cover_letter_text": (
            "비전공자이지만 데이터를 통해 사용자의 행동 패턴을 파악하고 문제를 해결하는 과정에 흥미를 느꼈습니다. "
            "프로젝트를 통해 데이터 전처리, 모델 비교, 결과 해석의 중요성을 배웠습니다."
        ),
        "jd_text": (
            "데이터 분석가 인턴 채용. SQL 기반 데이터 추출, Python 기반 데이터 분석, "
            "대시보드 작성, 지표 정의 경험을 요구합니다. 통계적 사고와 커뮤니케이션 능력을 중요하게 봅니다."
        ),
        "missing_fields": ["business_impact", "dashboard_experience"],
    },
    "user_003": {
        "document_id": "doc_003",
        "resume_text": (
            "AI 엔지니어로 2년간 근무하며 RAG 기반 사내 문서 검색 챗봇을 개발했습니다. "
            "문서 chunking, embedding, vector search, reranking 파이프라인을 설계했고, "
            "검색 품질 개선을 위해 메타데이터 필터와 hybrid retrieval 방식을 적용했습니다."
        ),
        "cover_letter_text": (
            "LLM 서비스 개발에서 중요한 것은 모델 성능뿐 아니라 검색 품질, 응답 안정성, 비용 관리라고 생각합니다. "
            "이전 프로젝트에서 검색 결과가 부정확해지는 문제를 발견하고 chunk 크기와 reranking 기준을 조정하여 품질을 개선했습니다."
        ),
        "jd_text": (
            "AI 엔지니어 채용. LLM/RAG 서비스 개발 경험, Vector DB 사용 경험, "
            "LangChain 또는 LangGraph 기반 파이프라인 구축 경험, 검색 품질 평가 경험을 요구합니다."
        ),
        "missing_fields": ["quantitative_result"],
    },
}


MOCK_EVALUATION = {
    "evaluation_id": "eval_001",
    "question_id": "q_001",
    "answer": "팀원들이 Django를 써본 적이 있고 인증 기능이 있어서 빠르게 개발할 수 있다고 생각했습니다.",
    "score": 3,
    "strengths": [
        "Django 선택 이유로 개발 속도와 인증 기능을 언급함",
        "팀 상황을 고려한 기술 선택이었다는 점을 설명함",
    ],
    "weaknesses": [
        "FastAPI나 Flask와의 구체적인 비교가 부족함",
        "프로젝트 요구사항과 기술 선택을 연결하는 설명이 약함",
    ],
    "missing_keywords": ["대안 비교", "트레이드오프", "프로젝트 요구사항"],
    "weakness_tags": ["weak_technical_reasoning", "lack_of_specificity"],
}


def get_mock_user(user_id: str) -> dict[str, Any]:
    for user in MOCK_USERS:
        if user["user_id"] == user_id:
            return user
    raise ValueError(f"mock user not found: {user_id}")


def get_mock_document(user_id: str) -> dict[str, Any]:
    try:
        return MOCK_DOCUMENTS[user_id]
    except KeyError as exc:
        raise ValueError(f"mock document not found: {user_id}") from exc
