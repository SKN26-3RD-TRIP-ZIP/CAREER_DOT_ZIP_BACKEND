"""
공통 픽스처 및 샘플 데이터

지원자 프로필 4종:
  entry_junior    신입 (0년, 대졸, 프로젝트만)
  junior          주니어 (1.5년, 대졸)
  mid             미드레벨 (3년, 대졸)
  senior          시니어 (6년, 석사)

JD 요건 4종:
  jd_entry        신입 가능 (min_years=0)
  jd_junior       2년+ (대졸, 백엔드)
  jd_mid          3년+ (대졸, 백엔드)
  jd_senior       5년+ (석사이상, 백엔드)
"""

import pytest


# ──────────────────────────────────────────────
# 지원자 이력서 분석 결과 (analyze_resume 반환값 형식)
# ──────────────────────────────────────────────

@pytest.fixture
def resume_entry():
    return {
        "tech_stack":          ["Python", "Django", "MySQL", "Git"],
        "key_experiences":     ["팀 프로젝트에서 REST API 5개 설계"],
        "strengths":           ["빠른 학습력 (2주 내 Django 습득)"],
        "trait_evidence":      ["팀원과 코드리뷰를 통해 품질을 개선한 경험"],
        "projects": [
            {"name": "중고거래앱", "role": "백엔드 개발", "tech": ["Python", "Django"], "result": "팀 프로젝트 완성", "domain": "e-commerce"}
        ],
        "years_of_experience": 0,
        "education":           "대졸",
        "career_level":        "entry",
    }


@pytest.fixture
def resume_junior():
    return {
        "tech_stack":          ["Python", "Django", "PostgreSQL", "Redis", "Docker", "Git"],
        "key_experiences":     ["스타트업에서 백엔드 API 20개 설계 및 운영", "Redis 캐싱으로 응답 속도 40% 개선"],
        "strengths":           ["성능 최적화 경험 (Redis, 쿼리 튜닝)"],
        "trait_evidence":      ["데이터를 근거로 팀 의사결정을 이끈 경험"],
        "projects": [
            {"name": "배달플랫폼", "role": "백엔드 리드", "tech": ["Python", "Django", "Redis"], "result": "DAU 3천 달성", "domain": "logistics"}
        ],
        "years_of_experience": 1.5,
        "education":           "대졸",
        "career_level":        "experienced",
    }


@pytest.fixture
def resume_mid():
    return {
        "tech_stack":          ["Python", "Django", "FastAPI", "PostgreSQL", "Redis", "Kubernetes", "Docker", "AWS"],
        "key_experiences":     ["마이크로서비스 아키텍처 설계 및 도입", "K8s 클러스터 운영 (노드 10대)"],
        "strengths":           ["시스템 설계 역량", "DevOps 경험"],
        "trait_evidence":      ["주도적으로 기술 스택 전환을 제안하고 실행한 경험"],
        "projects": [
            {"name": "핀테크플랫폼", "role": "백엔드 리드", "tech": ["FastAPI", "Kubernetes", "AWS"], "result": "거래량 10배 증가 대응", "domain": "fintech"}
        ],
        "years_of_experience": 3,
        "education":           "대졸",
        "career_level":        "experienced",
    }


@pytest.fixture
def resume_senior():
    return {
        "tech_stack":          ["Python", "Java", "Spring Boot", "Kafka", "Kubernetes", "AWS", "Terraform", "PostgreSQL"],
        "key_experiences":     ["100만 MAU 서비스 백엔드 아키텍처 설계", "Kafka 기반 이벤트 드리븐 시스템 구축"],
        "strengths":           ["대규모 시스템 설계", "팀 리딩 (5명)"],
        "trait_evidence":      ["복잡한 기술 문제를 단순화해 팀에 전달한 경험"],
        "projects": [
            {"name": "커머스플랫폼", "role": "아키텍트", "tech": ["Java", "Kafka", "Kubernetes"], "result": "MAU 100만 안정 운영", "domain": "e-commerce"}
        ],
        "years_of_experience": 6,
        "education":           "석사이상",
        "career_level":        "experienced",
    }


# ──────────────────────────────────────────────
# JD 키워드 (extract_jd_keywords 반환값 형식)
# ──────────────────────────────────────────────

@pytest.fixture
def jd_keywords_backend():
    return {
        "tech_keywords":  ["Python", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes"],
        "trait_keywords": ["주도적으로 문제를 해결하는 분", "데이터 기반으로 의사결정하는 분", "커뮤니케이션이 원활한 분"],
    }


@pytest.fixture
def jd_keywords_fullstack():
    return {
        "tech_keywords":  ["React", "TypeScript", "Node.js", "PostgreSQL", "AWS"],
        "trait_keywords": ["자기주도적으로 학습하는 분", "팀플레이를 즐기는 분"],
    }


# ──────────────────────────────────────────────
# JD 자격 요건 (extract_jd_requirements 반환값 형식)
# ──────────────────────────────────────────────

@pytest.fixture
def jd_req_entry():
    return {
        "min_years":      0,
        "education":      "대졸",
        "job_type":       "백엔드",
        "required_tech":  ["Python", "Django"],
        "preferred_tech": ["Docker", "Redis"],
    }


@pytest.fixture
def jd_req_junior():
    return {
        "min_years":      2,
        "education":      "대졸",
        "job_type":       "백엔드",
        "required_tech":  ["Python", "Django", "PostgreSQL"],
        "preferred_tech": ["Redis", "Docker"],
    }


@pytest.fixture
def jd_req_mid():
    return {
        "min_years":      3,
        "education":      "대졸",
        "job_type":       "백엔드",
        "required_tech":  ["Python", "Django", "Redis", "Docker"],
        "preferred_tech": ["Kubernetes", "AWS"],
    }


@pytest.fixture
def jd_req_senior():
    return {
        "min_years":      5,
        "education":      "석사이상",
        "job_type":       "백엔드",
        "required_tech":  ["Python", "Kubernetes", "Kafka"],
        "preferred_tech": ["Terraform", "AWS"],
    }


# ──────────────────────────────────────────────
# trait_details (임베딩 유사도 계산 결과 형식)
# ──────────────────────────────────────────────

@pytest.fixture
def trait_details_high():
    return [
        {"trait": "주도적으로 문제를 해결하는 분", "best_match": "주도적으로 기술 스택 전환을 제안", "similarity": 0.82},
        {"trait": "데이터 기반으로 의사결정하는 분", "best_match": "데이터를 근거로 팀 의사결정", "similarity": 0.78},
        {"trait": "커뮤니케이션이 원활한 분",       "best_match": "팀원과 코드리뷰를 통해 품질 개선", "similarity": 0.71},
    ]


@pytest.fixture
def trait_details_mixed():
    return [
        {"trait": "주도적으로 문제를 해결하는 분", "best_match": "팀 프로젝트에서 API 설계", "similarity": 0.61},
        {"trait": "데이터 기반으로 의사결정하는 분", "best_match": "팀 프로젝트 완성",         "similarity": 0.38},
        {"trait": "커뮤니케이션이 원활한 분",       "best_match": "코드리뷰 경험",             "similarity": 0.45},
    ]


@pytest.fixture
def trait_details_low():
    return [
        {"trait": "주도적으로 문제를 해결하는 분", "best_match": "REST API 설계", "similarity": 0.32},
        {"trait": "데이터 기반으로 의사결정하는 분", "best_match": "팀 프로젝트",  "similarity": 0.28},
        {"trait": "커뮤니케이션이 원활한 분",       "best_match": "팀원과 협업",   "similarity": 0.41},
    ]
