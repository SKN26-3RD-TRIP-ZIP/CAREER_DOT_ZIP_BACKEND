"""
resume_service 프롬프트 품질 테스트 (실제 GPT 호출)

테스트 대상:
  analyze_resume()
    - tech_stack / key_experiences / strengths / trait_evidence / projects
    - years_of_experience / education / career_level

주의:
  실제 OpenAI API를 호출합니다. OPENAI_API_KEY 환경변수가 필요합니다.
  GPT 응답 비결정성으로 인해 타입·범위·포함 여부를 검증합니다.

실행:
  pytest apps/analysis/tests/test_resume_service.py -v -s
  pytest apps/analysis/tests/test_resume_service.py -v -s -k "entry"
"""

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")
from apps.analysis.services.resume_service import analyze_resume


# ══════════════════════════════════════════════════════════════
# 샘플 이력서 + 자소서 텍스트
# ══════════════════════════════════════════════════════════════

# 1. 신입 — 프로젝트만 있고 실무 경험 없음 | 대졸 재학 중
RESUME_ENTRY = """
[학력]
- 한국대학교 컴퓨터공학과 재학 중 (졸업예정 2026.02)

[기술 스택]
- Python, Django, MySQL, Git, Docker (기초)

[프로젝트]
- 중고거래 플랫폼 (팀 3인, 백엔드 개발, 2024.09~2024.12)
  - Django REST Framework 기반 API 8개 설계 및 구현
  - MySQL 스키마 설계, JWT 인증 구현
  - 결과: 팀 프로젝트 완성, GitHub 배포
"""

CL_ENTRY = """
저는 문제를 만나면 포기하지 않고 끝까지 해결하려는 성향을 가지고 있습니다.
프로젝트 도중 JWT 토큰 만료 오류가 반복될 때, 혼자 공식 문서와 스택오버플로우를 3일 동안 탐색해
결국 refresh token rotation 방식으로 해결한 경험이 있습니다.
팀원과의 소통을 중요하게 생각해, 매주 코드 리뷰 시간을 직접 제안하고 운영했습니다.
"""

# 2. 경력 2년 | 스타트업 백엔드 | 대졸
RESUME_EXPERIENCED = """
[학력]
- 서울과학기술대학교 소프트웨어공학과 졸업 (2022.02)

[경력]
- (주)패스트딜리버리 백엔드 개발자 (2022.03 ~ 2024.02, 2년)
  - Django 기반 배달 플랫폼 API 개발 (총 30개 이상)
  - Redis 캐싱 도입으로 API 응답 속도 40% 개선
  - 주문 상태 관리 모듈 설계 및 구현

[기술 스택]
- Python, Django, PostgreSQL, Redis, Docker, Git, AWS EC2/S3

[프로젝트]
- 사이드 프로젝트: 독서 기록 앱 (개인, 2024.03~2024.06)
  - FastAPI + PostgreSQL 기반 REST API
  - 결과: 앱스토어 출시, 월 100명 사용
"""

CL_EXPERIENCED = """
저는 성능 문제를 데이터로 접근하는 방식을 선호합니다.
배달 플랫폼에서 주문 조회 API의 응답 시간이 평균 1.2초였을 때,
쿼리 프로파일링을 통해 N+1 문제를 발견하고 select_related와 Redis 캐싱을 조합해
응답 시간을 0.3초로 줄인 경험이 있습니다.
의사결정 시 항상 측정 가능한 지표를 기준으로 팀을 설득해왔습니다.
"""

# 3. 자소서 없는 케이스 (빈 문자열)
RESUME_NO_CL = """
[학력]
- 부산대학교 전자공학과 졸업 (2021.02)

[경력]
- (주)클라우드원 DevOps 엔지니어 (2021.03 ~ 2024.03, 3년)
  - Kubernetes 클러스터 운영 (노드 15대)
  - Terraform으로 AWS 인프라 코드화
  - CI/CD 파이프라인 구축 (GitHub Actions + ArgoCD)

[기술 스택]
- Python, Kubernetes, Terraform, AWS, Docker, GitHub Actions, ArgoCD
"""

CL_EMPTY = ""

# 4. 석사 | 경력 없음 | 연구 중심
RESUME_MASTER = """
[학력]
- 카이스트 인공지능대학원 석사 재학 중 (2024.03~)
- 연세대학교 컴퓨터공학과 학사 졸업 (2024.02)

[연구]
- NLP 기반 이력서 매칭 알고리즘 연구 (지도교수 지도하에 진행 중)

[기술 스택]
- Python, PyTorch, Hugging Face, FastAPI, PostgreSQL

[프로젝트]
- 논문 구현: BERT 기반 문서 유사도 모델 (2024.06~2024.12)
  - Hugging Face 파인튜닝, 정확도 87% 달성
"""

CL_MASTER = """
저는 이론과 실무를 연결하는 것을 즐깁니다.
BERT 모델을 이력서 매칭에 적용하면서, 단순 키워드 매칭보다
문맥 기반 유사도가 30% 더 정확하다는 결과를 실험으로 검증했습니다.
연구 결과를 코드로 바로 구현해 검증하는 방식을 선호합니다.
"""


# ══════════════════════════════════════════════════════════════
# 공통 구조 검증
# ══════════════════════════════════════════════════════════════

def _assert_structure(result: dict):
    """반환 구조·타입 공통 검증"""
    assert isinstance(result.get("tech_stack"),           list),  f"tech_stack 타입 오류: {type(result.get('tech_stack'))}"
    assert isinstance(result.get("key_experiences"),      list),  f"key_experiences 타입 오류"
    assert isinstance(result.get("strengths"),            list),  f"strengths 타입 오류"
    assert isinstance(result.get("trait_evidence"),       list),  f"trait_evidence 타입 오류"
    assert isinstance(result.get("projects"),             list),  f"projects 타입 오류"
    assert isinstance(result.get("years_of_experience"),  (int, float)), f"years_of_experience 타입 오류"
    assert result.get("education")    in {"고졸", "대졸", "석사이상"},    f"education 범위 초과: {result.get('education')}"
    assert result.get("career_level") in {"entry", "experienced"},       f"career_level 범위 초과: {result.get('career_level')}"
    assert result["years_of_experience"] >= 0, f"years_of_experience 음수: {result['years_of_experience']}"


def _assert_projects_structure(projects: list):
    """projects 배열의 각 항목 필드 검증"""
    required_keys = {"name", "role", "tech", "result", "domain"}
    for i, p in enumerate(projects):
        missing = required_keys - set(p.keys())
        assert not missing, f"projects[{i}] 누락 필드: {missing} / 전체: {p}"
        assert isinstance(p["tech"], list), f"projects[{i}].tech가 list가 아님: {p['tech']}"


# ══════════════════════════════════════════════════════════════
# 신입 케이스
# ══════════════════════════════════════════════════════════════

class TestAnalyzeResumeEntry:

    def test_기본_구조(self):
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 구조] {result}")
        _assert_structure(result)

    def test_career_level_entry_반환(self):
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 career_level] {result['career_level']}")
        assert result["career_level"] == "entry", \
            f"프로젝트만 있는 신입인데 career_level={result['career_level']}"

    def test_years_of_experience_0(self):
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 연차] {result['years_of_experience']}")
        assert result["years_of_experience"] == 0, \
            f"실무 경험 없는 신입인데 years_of_experience={result['years_of_experience']}"

    def test_education_대졸(self):
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 학력] {result['education']}")
        assert result["education"] == "대졸", \
            f"대학 재학 중인데 education={result['education']}"

    def test_tech_stack_추출(self):
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 기술] {result['tech_stack']}")
        assert len(result["tech_stack"]) > 0, "tech_stack이 비어 있음"
        tech_lower = [t.lower() for t in result["tech_stack"]]
        assert any("python" in t for t in tech_lower), f"Python이 tech_stack에 없음: {result['tech_stack']}"
        assert any("django" in t for t in tech_lower), f"Django가 tech_stack에 없음: {result['tech_stack']}"

    def test_projects_구조(self):
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 프로젝트] {result['projects']}")
        assert len(result["projects"]) > 0, "프로젝트가 있는데 projects가 비어 있음"
        _assert_projects_structure(result["projects"])

    def test_trait_evidence_자소서_근거(self):
        """자소서에 기술된 행동 증거가 trait_evidence에 반영되어야 함"""
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 인재상 증거] {result['trait_evidence']}")
        assert len(result["trait_evidence"]) > 0, "자소서가 있는데 trait_evidence가 비어 있음"
        # 단순 단어 단독 추출 금지 검증
        for ev in result["trait_evidence"]:
            assert len(ev) > 10, f"trait_evidence가 너무 짧음 (단어 단독 추출 의심): '{ev}'"

    def test_strengths_추상어_단독_금지(self):
        """'성실', '열정' 같은 추상어만 단독으로 나오면 안 됨"""
        result = analyze_resume(RESUME_ENTRY, CL_ENTRY)
        print(f"\n[신입 강점] {result['strengths']}")
        banned_alone = {"성실", "열정", "책임감", "긍정적"}
        for s in result["strengths"]:
            assert s.strip() not in banned_alone, \
                f"추상어 단독 추출: '{s}' — 근거 포함 형태여야 함"


# ══════════════════════════════════════════════════════════════
# 경력 케이스
# ══════════════════════════════════════════════════════════════

class TestAnalyzeResumeExperienced:

    def test_기본_구조(self):
        result = analyze_resume(RESUME_EXPERIENCED, CL_EXPERIENCED)
        print(f"\n[경력 구조] {result}")
        _assert_structure(result)

    def test_career_level_experienced(self):
        result = analyze_resume(RESUME_EXPERIENCED, CL_EXPERIENCED)
        print(f"\n[경력 career_level] {result['career_level']}")
        assert result["career_level"] == "experienced", \
            f"2년 경력인데 career_level={result['career_level']}"

    def test_years_of_experience_2년(self):
        result = analyze_resume(RESUME_EXPERIENCED, CL_EXPERIENCED)
        print(f"\n[경력 연차] {result['years_of_experience']}")
        assert result["years_of_experience"] >= 1.5, \
            f"2년 경력인데 years_of_experience={result['years_of_experience']}"

    def test_education_대졸(self):
        result = analyze_resume(RESUME_EXPERIENCED, CL_EXPERIENCED)
        assert result["education"] == "대졸", \
            f"대졸인데 education={result['education']}"

    def test_사이드프로젝트_포함(self):
        """사이드 프로젝트도 projects에 포함되어야 함"""
        result = analyze_resume(RESUME_EXPERIENCED, CL_EXPERIENCED)
        print(f"\n[경력 프로젝트] {result['projects']}")
        assert len(result["projects"]) >= 1, "사이드 프로젝트가 있는데 projects가 비어 있음"
        _assert_projects_structure(result["projects"])

    def test_key_experiences_실무_중심(self):
        """key_experiences에 실무에서 주도한 내용이 포함되어야 함"""
        result = analyze_resume(RESUME_EXPERIENCED, CL_EXPERIENCED)
        print(f"\n[경력 핵심 경험] {result['key_experiences']}")
        assert len(result["key_experiences"]) > 0, "key_experiences가 비어 있음"
        # 각 항목이 단순 단어가 아닌 문장 형태여야 함
        for exp in result["key_experiences"]:
            assert len(exp) > 10, f"key_experiences 항목이 너무 짧음: '{exp}'"


# ══════════════════════════════════════════════════════════════
# 자소서 없는 케이스
# ══════════════════════════════════════════════════════════════

class TestAnalyzeResumeNoCoverLetter:

    def test_자소서_없어도_정상_반환(self):
        result = analyze_resume(RESUME_NO_CL, CL_EMPTY)
        print(f"\n[자소서 없음] {result}")
        _assert_structure(result)

    def test_3년_경력_experienced(self):
        result = analyze_resume(RESUME_NO_CL, CL_EMPTY)
        assert result["career_level"] == "experienced", \
            f"3년 경력인데 career_level={result['career_level']}"
        assert result["years_of_experience"] >= 2.5, \
            f"3년 경력인데 years_of_experience={result['years_of_experience']}"

    def test_devops_기술_추출(self):
        result = analyze_resume(RESUME_NO_CL, CL_EMPTY)
        print(f"\n[DevOps 기술] {result['tech_stack']}")
        tech_lower = [t.lower() for t in result["tech_stack"]]
        assert any("kubernetes" in t for t in tech_lower), \
            f"Kubernetes가 tech_stack에 없음: {result['tech_stack']}"
        assert any("terraform" in t for t in tech_lower), \
            f"Terraform이 tech_stack에 없음: {result['tech_stack']}"


# ══════════════════════════════════════════════════════════════
# 석사 케이스
# ══════════════════════════════════════════════════════════════

class TestAnalyzeResumeMaster:

    def test_기본_구조(self):
        result = analyze_resume(RESUME_MASTER, CL_MASTER)
        print(f"\n[석사 구조] {result}")
        _assert_structure(result)

    def test_education_석사이상(self):
        result = analyze_resume(RESUME_MASTER, CL_MASTER)
        print(f"\n[석사 학력] {result['education']}")
        assert result["education"] == "석사이상", \
            f"석사 재학 중인데 education={result['education']}"

    def test_실무경험_없으므로_entry(self):
        result = analyze_resume(RESUME_MASTER, CL_MASTER)
        print(f"\n[석사 career_level] {result['career_level']}")
        assert result["career_level"] == "entry", \
            f"실무 경험 없는 석사인데 career_level={result['career_level']}"

    def test_years_of_experience_0(self):
        result = analyze_resume(RESUME_MASTER, CL_MASTER)
        print(f"\n[석사 연차] {result['years_of_experience']}")
        assert result["years_of_experience"] == 0, \
            f"실무 경험 없는데 years_of_experience={result['years_of_experience']}"

    def test_연구프로젝트_포함(self):
        result = analyze_resume(RESUME_MASTER, CL_MASTER)
        print(f"\n[석사 프로젝트] {result['projects']}")
        assert len(result["projects"]) > 0, "연구 프로젝트가 있는데 projects가 비어 있음"
        _assert_projects_structure(result["projects"])
