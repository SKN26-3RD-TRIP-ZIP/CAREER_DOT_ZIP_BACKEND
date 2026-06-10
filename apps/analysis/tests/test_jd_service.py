"""
jd_service 프롬프트 품질 테스트 (실제 GPT 호출)

테스트 대상:
  extract_jd_keywords()     tech_keywords / trait_keywords 분리 추출
  extract_jd_requirements() min_years / education / job_type / required_tech / preferred_tech 추출

주의:
  실제 OpenAI API를 호출합니다. OPENAI_API_KEY 환경변수가 필요합니다.
  GPT 응답 비결정성으로 인해 엄격한 값 일치 대신 타입·범위·포함 여부를 검증합니다.

실행:
  pytest apps/analysis/tests/test_jd_service.py -v -s
  pytest apps/analysis/tests/test_jd_service.py -v -s -k "requirements"
"""

import pytest
from apps.analysis.services.jd_service import extract_jd_keywords, extract_jd_requirements


# ══════════════════════════════════════════════════════════════
# 샘플 JD 텍스트
# ══════════════════════════════════════════════════════════════

# 1. 신입 가능 | 백엔드 | Python/Django 명시
JD_ENTRY_BACKEND = """
[회사] 커리어닷집 (스타트업)
[직무] 백엔드 개발자

[담당 업무]
- Django REST Framework 기반 API 설계 및 개발
- PostgreSQL 스키마 설계 및 쿼리 최적화
- Docker 기반 배포 환경 구성

[자격 요건]
- Python, Django 활용 가능하신 분
- 신입 지원 가능 (학력 무관)

[우대 사항]
- Redis 사용 경험
- AWS 기본 지식
- 팀 프로젝트 경험이 있으신 분
- 커뮤니케이션을 중요하게 생각하는 분
"""

# 2. 경력 3년 이상 | 백엔드 | 범위 표현 "3~5년"
JD_MID_RANGE_YEARS = """
[회사] 핀크(Fink) - 핀테크 스타트업
[직무] 백엔드 개발자 (Python)

[담당 업무]
- 결제/정산 API 개발 및 운영
- Kafka 기반 이벤트 파이프라인 구축
- Kubernetes 클러스터 운영

[자격 요건]
- Python 백엔드 개발 경력 3~5년
- Django 또는 FastAPI 실무 경험
- PostgreSQL 설계 및 최적화 경험
- 대졸 이상

[우대 사항]
- Kubernetes 운영 경험
- Terraform 사용 경험
- 주도적으로 기술 문제를 해결하고 팀에 공유하는 분
- 빠르게 변화하는 환경에서 적응력이 뛰어난 분
"""

# 3. 경력 5년 이상 | 시니어 | 석사 우대
JD_SENIOR_ARCHITECT = """
[회사] 대형 커머스 플랫폼 (직원 500+)
[직무] 백엔드 아키텍트 / 시니어 개발자

[담당 업무]
- 대규모 트래픽 처리를 위한 시스템 아키텍처 설계
- Java(Spring Boot), Python 기반 마이크로서비스 구축
- 기술 로드맵 수립 및 주니어 멘토링

[자격 요건]
- 백엔드 개발 경력 5년 이상
- Java, Python 중 1개 이상 능숙
- Kafka, RabbitMQ 등 메시지 브로커 경험
- 석사 이상 우대

[우대 사항]
- AWS, GCP 중 1개 이상 운영 경험
- Terraform 또는 IaC 경험
- 대규모 팀에서 기술 리더십을 발휘한 경험이 있는 분
- 복잡한 문제를 단순하게 설명할 수 있는 분
"""

# 4. 경력 무관 명시 | 프론트엔드
JD_ENTRY_FRONTEND = """
[회사] 디자인테크 (중소기업)
[직무] 프론트엔드 개발자

[담당 업무]
- React 기반 웹 서비스 개발 및 유지보수
- TypeScript, Next.js 활용

[자격 요건]
- React 개발 경험 보유자
- 경력 무관 (신입/경력 모두 지원 가능)
- 고졸 이상

[우대 사항]
- Next.js, TypeScript 사용 경험
- 자기주도적으로 학습하고 성장하는 분
- 팀원과 원활하게 소통하는 분
"""

# 5. 학력 무관 | 연차 미명시 | 풀스택
JD_NO_CONSTRAINTS = """
[회사] 글로벌 SaaS 스타트업
[직무] 풀스택 개발자

[담당 업무]
- Node.js(Express) 백엔드 개발
- React 프론트엔드 개발
- AWS 인프라 관리

[자격 요건]
- Node.js, React 개발 가능한 분
- 학력·경력 무관

[우대 사항]
- TypeScript 경험
- PostgreSQL 사용 경험
- 빠른 실행력과 오너십을 가진 분
"""


# ══════════════════════════════════════════════════════════════
# extract_jd_requirements 테스트
# ══════════════════════════════════════════════════════════════

class TestExtractJdRequirements:

    def _assert_structure(self, result: dict):
        """반환 구조·타입 공통 검증"""
        assert isinstance(result["min_years"],      int),  f"min_years가 int가 아님: {result['min_years']}"
        assert isinstance(result["education"],       str),  f"education이 str이 아님: {result['education']}"
        assert isinstance(result["job_type"],        str),  f"job_type이 str이 아님: {result['job_type']}"
        assert isinstance(result["required_tech"],   list), f"required_tech가 list가 아님: {result['required_tech']}"
        assert isinstance(result["preferred_tech"],  list), f"preferred_tech가 list가 아님: {result['preferred_tech']}"
        assert result["education"] in {"무관", "고졸", "대졸", "석사이상"}, \
            f"education 값 범위 초과: {result['education']}"
        assert result["min_years"] >= 0, f"min_years 음수: {result['min_years']}"

    def test_신입가능_백엔드_기본구조(self):
        result = extract_jd_requirements(JD_ENTRY_BACKEND)
        print(f"\n[신입 백엔드] {result}")

        self._assert_structure(result)
        assert result["min_years"] == 0, f"신입 JD인데 min_years={result['min_years']}"
        assert "백엔드" in result["job_type"] or result["job_type"] == "", \
            f"job_type 예상값 불일치: {result['job_type']}"

    def test_신입가능_백엔드_필수기술_추출(self):
        result = extract_jd_requirements(JD_ENTRY_BACKEND)
        print(f"\n[신입 백엔드 기술] required={result['required_tech']} preferred={result['preferred_tech']}")

        assert len(result["required_tech"]) > 0, "required_tech가 비어 있음"
        required_lower = [t.lower() for t in result["required_tech"]]
        assert any("python" in t for t in required_lower), \
            f"Python이 required_tech에 없음: {result['required_tech']}"
        assert any("django" in t for t in required_lower), \
            f"Django가 required_tech에 없음: {result['required_tech']}"

    def test_신입가능_백엔드_우대기술_필수와_분리(self):
        result = extract_jd_requirements(JD_ENTRY_BACKEND)
        print(f"\n[신입 백엔드 우대] {result['preferred_tech']}")

        required_lower  = [t.lower() for t in result["required_tech"]]
        preferred_lower = [t.lower() for t in result["preferred_tech"]]
        overlap = set(required_lower) & set(preferred_lower)
        assert len(overlap) == 0, f"required/preferred 중복 항목: {overlap}"

    def test_범위표현_연차_하한값_추출(self):
        """'3~5년' → min_years=3"""
        result = extract_jd_requirements(JD_MID_RANGE_YEARS)
        print(f"\n[3~5년 JD] min_years={result['min_years']}")

        assert result["min_years"] == 3, \
            f"'3~5년' 표현의 하한값은 3이어야 함, 실제: {result['min_years']}"

    def test_범위표현_연차_대졸이상_학력(self):
        result = extract_jd_requirements(JD_MID_RANGE_YEARS)
        print(f"\n[3~5년 JD 학력] {result['education']}")

        assert result["education"] == "대졸", \
            f"'대졸 이상' → '대졸' 이어야 함, 실제: {result['education']}"

    def test_시니어_5년이상_연차(self):
        result = extract_jd_requirements(JD_SENIOR_ARCHITECT)
        print(f"\n[시니어 JD] min_years={result['min_years']}")

        assert result["min_years"] >= 5, \
            f"5년 이상 JD인데 min_years={result['min_years']}"

    def test_시니어_석사이상_학력(self):
        result = extract_jd_requirements(JD_SENIOR_ARCHITECT)
        print(f"\n[시니어 학력] {result['education']}")

        assert result["education"] == "석사이상", \
            f"'석사 이상 우대' → '석사이상' 이어야 함, 실제: {result['education']}"

    def test_경력무관_명시시_0반환(self):
        result = extract_jd_requirements(JD_ENTRY_FRONTEND)
        print(f"\n[경력 무관] min_years={result['min_years']}")

        assert result["min_years"] == 0, \
            f"'경력 무관' JD인데 min_years={result['min_years']}"

    def test_경력무관_고졸이상_학력(self):
        result = extract_jd_requirements(JD_ENTRY_FRONTEND)
        print(f"\n[프론트 학력] {result['education']}")

        assert result["education"] == "고졸", \
            f"'고졸 이상' → '고졸' 이어야 함, 실제: {result['education']}"

    def test_프론트엔드_job_type(self):
        result = extract_jd_requirements(JD_ENTRY_FRONTEND)
        print(f"\n[프론트 job_type] {result['job_type']}")

        assert "프론트" in result["job_type"], \
            f"프론트엔드 JD의 job_type 불일치: {result['job_type']}"

    def test_연차미명시_학력무관_모두_0반환(self):
        result = extract_jd_requirements(JD_NO_CONSTRAINTS)
        print(f"\n[무제한 JD] min_years={result['min_years']} education={result['education']}")

        assert result["min_years"] == 0, \
            f"연차 미명시 JD인데 min_years={result['min_years']}"
        assert result["education"] == "무관", \
            f"학력 무관 JD인데 education={result['education']}"

    def test_풀스택_job_type(self):
        result = extract_jd_requirements(JD_NO_CONSTRAINTS)
        print(f"\n[풀스택 job_type] {result['job_type']}")

        assert "풀스택" in result["job_type"] or result["job_type"] != "", \
            f"풀스택 JD job_type이 비어 있음: {result['job_type']}"


# ══════════════════════════════════════════════════════════════
# extract_jd_keywords 테스트
# ══════════════════════════════════════════════════════════════

class TestExtractJdKeywords:

    def _assert_structure(self, result: dict):
        assert isinstance(result["tech_keywords"],  list), f"tech_keywords가 list가 아님"
        assert isinstance(result["trait_keywords"], list), f"trait_keywords가 list가 아님"
        assert len(result["tech_keywords"])  > 0, "tech_keywords가 비어 있음"
        assert len(result["trait_keywords"]) > 0, "trait_keywords가 비어 있음"

    def test_백엔드_기본_구조(self):
        result = extract_jd_keywords(JD_ENTRY_BACKEND)
        print(f"\n[키워드 백엔드] tech={result['tech_keywords']} trait={result['trait_keywords']}")

        self._assert_structure(result)

    def test_백엔드_tech_키워드_포함(self):
        result = extract_jd_keywords(JD_ENTRY_BACKEND)
        tech_lower = [t.lower() for t in result["tech_keywords"]]

        assert any("python" in t for t in tech_lower), \
            f"Python이 tech_keywords에 없음: {result['tech_keywords']}"
        assert any("django" in t for t in tech_lower), \
            f"Django가 tech_keywords에 없음: {result['tech_keywords']}"

    def test_trait_키워드_기술스택_미포함(self):
        """인재상에 Python, Django 같은 기술명이 섞이면 안 됨"""
        result = extract_jd_keywords(JD_MID_RANGE_YEARS)
        print(f"\n[인재상 키워드] {result['trait_keywords']}")

        tech_terms = {"python", "django", "fastapi", "postgresql", "kafka", "kubernetes", "terraform"}
        for trait in result["trait_keywords"]:
            trait_lower = trait.lower()
            assert not any(term == trait_lower for term in tech_terms), \
                f"trait_keywords에 기술명이 포함됨: '{trait}'"

    def test_시니어_trait_키워드_문맥포함(self):
        """인재상이 단어 단독이 아닌 구/절 형태여야 함"""
        result = extract_jd_keywords(JD_SENIOR_ARCHITECT)
        print(f"\n[시니어 인재상] {result['trait_keywords']}")

        for trait in result["trait_keywords"]:
            assert len(trait) > 5, \
                f"trait 키워드가 너무 짧음 (단어 단독 추출 의심): '{trait}'"

    def test_tech_trait_중복없음(self):
        result = extract_jd_keywords(JD_MID_RANGE_YEARS)
        tech_lower  = {t.lower() for t in result["tech_keywords"]}
        trait_lower = {t.lower() for t in result["trait_keywords"]}

        overlap = tech_lower & trait_lower
        assert len(overlap) == 0, f"tech/trait 중복 키워드: {overlap}"
