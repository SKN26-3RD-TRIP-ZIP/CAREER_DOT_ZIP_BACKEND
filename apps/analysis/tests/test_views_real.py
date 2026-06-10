"""
analysis 파이프라인 실제 GPT 호출 통합 테스트 (DB 없음)

목적:
  실제 JD / 이력서 / 자소서 텍스트를 넣었을 때
  각 서비스 함수가 어떤 데이터를 반환하는지 확인한다.

  DB 연결 없이 서비스 함수를 직접 호출합니다.
  (views → _run_analysis 는 DB에 결합되어 있으므로 서비스 레이어를 직접 호출)

주의:
  실제 OpenAI API를 호출합니다. OPENAI_API_KEY 환경변수가 필요합니다.
  시나리오당 약 30~60초 소요됩니다.

실행:
  pytest apps/analysis/tests/test_views_real.py -v -s
  pytest apps/analysis/tests/test_views_real.py -v -s -k "신입"
  pytest apps/analysis/tests/test_views_real.py -v -s -k "경력_매칭"
  pytest apps/analysis/tests/test_views_real.py -v -s -k "경력_미스매치"
  pytest apps/analysis/tests/test_views_real.py -v -s -k "전체_파이프라인"
"""

import pprint
from concurrent.futures import ThreadPoolExecutor
from django.test import SimpleTestCase

from apps.analysis.services.jd_service      import extract_jd_keywords, extract_jd_requirements
from apps.analysis.services.resume_service  import analyze_resume
from apps.analysis.services.match_service   import calculate_match_score
from apps.analysis.services.result_service  import build_match_result
from apps.analysis.services.gap_service     import calculate_gap, build_gap_message
from apps.analysis.services.question_gen_service  import generate_questions
from apps.analysis.services.question_merge_service import merge_and_deduplicate
from apps.analysis.services.star_service    import generate_star_answers
from apps.analysis.services.question_output_service import build_question_output


# ══════════════════════════════════════════════════════════════
# 시나리오 데이터
# ══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────
# 시나리오 1: 신입 — 프로젝트 경험만 있는 취준생
# ─────────────────────────────────────────

JD_STARTUP_BACKEND = """
[회사명] 커리어닷집 (스타트업, 30인)
[직무명] 백엔드 개발자 (Python/Django)
[고용 형태] 정규직

[담당 업무]
- Django REST Framework 기반 API 서버 설계·개발·운영
- PostgreSQL 스키마 설계 및 쿼리 최적화
- Celery + Redis를 활용한 비동기 작업 처리
- Docker 기반 컨테이너 환경 구성 및 AWS EC2/S3 배포

[자격 요건]
- Python 개발 경험 1년 이상 또는 그에 준하는 프로젝트 경험
- Django 또는 Flask 기반 REST API 개발 경험
- Git을 활용한 협업 경험
- 학력 무관

[우대 사항]
- Redis, Celery 사용 경험
- AWS 기본 서비스(EC2, S3, RDS) 운영 경험
- 스타트업 또는 팀 프로젝트 경험
- 스스로 문제를 찾아 해결하는 분
- 빠르게 배우고 실행하는 분
"""

RESUME_ENTRY_JUNIOR = """
[인적 사항]
이름: 김지원 | 연락처: 010-1234-5678 | 이메일: jiwon@example.com

[학력]
- 한국대학교 컴퓨터공학과 (2020.03 ~ 2024.02 졸업예정)

[기술 스택]
- 언어: Python, Java (기초)
- 프레임워크: Django, Django REST Framework
- 데이터베이스: MySQL, PostgreSQL (기초)
- 인프라: Git, Docker (기초), Linux 기본 명령어

[프로젝트]
1. 중고거래 플랫폼 "세컨핸즈" (팀 프로젝트, 4인, 2023.09 ~ 2023.12)
   - 역할: 백엔드 개발 (팀 내 백엔드 담당 2인 중 1인)
   - 기술: Python, Django REST Framework, PostgreSQL, JWT 인증
   - 구현 내용:
     * 회원가입/로그인 API (JWT), 상품 CRUD API 8개 설계 및 구현
     * PostgreSQL 테이블 설계 (ERD 작성), 인덱스 최적화 기초 적용
     * GitHub Actions를 이용한 간단한 CI 구성
   - 결과: 팀 프로젝트 완성, GitHub 500+ commits

2. 개인 블로그 API 서버 (개인 프로젝트, 2023.06 ~ 2023.08)
   - 기술: Python, Django, SQLite
   - 구현 내용: 게시글/댓글 CRUD, 태그 기반 검색 API
   - 결과: 개인 포트폴리오용, GitHub 배포

[수상/활동]
- 교내 해커톤 장려상 (2023.05)
- 알고리즘 스터디 참여 (2022.09 ~ 2023.06, 주 1회)
"""

CL_ENTRY_JUNIOR = """
[지원 동기]
저는 작은 아이디어가 실제 서비스로 구현되는 과정에서 큰 보람을 느끼는 개발자입니다.
커리어닷집이 취업 준비생의 실질적인 문제를 기술로 해결하려는 방향성에 깊이 공감해 지원했습니다.

[프로젝트 경험]
중고거래 플랫폼 프로젝트에서 백엔드를 담당하며 처음으로 REST API를 설계해봤습니다.
초반에 JWT 토큰 갱신 로직에서 무한 루프 버그가 발생했는데,
로그를 분석하고 공식 문서를 3일간 탐색한 끝에 refresh token rotation 방식으로 해결했습니다.

[협업 경험]
팀 프로젝트 중 API 응답 형식을 두고 프론트엔드 팀원과 의견 충돌이 있었습니다.
각자의 주장을 정리해 문서로 만들고, 실제 프론트 코드에서 어떤 형식이 더 편한지를
같이 확인하는 방식으로 합의를 이끌어냈습니다.

[성장 목표]
입사 후 6개월 안에 실 서비스 API를 독립적으로 설계·배포할 수 있는 수준에 도달하고 싶습니다.
Redis와 Celery를 실무에서 익히고, 점진적으로 시스템 설계 역량을 키워가겠습니다.
"""

# ─────────────────────────────────────────
# 시나리오 2: 경력 매칭 — JD 요건과 잘 맞는 경력자
# ─────────────────────────────────────────

JD_FINTECH_BACKEND = """
[회사명] 핀크(Fink) — 핀테크 스타트업 (Series B, 150인)
[직무명] 백엔드 개발자 (Python)
[고용 형태] 정규직

[담당 업무]
- 결제·정산 도메인 API 설계 및 운영 (Django/FastAPI)
- Kafka 기반 이벤트 드리븐 아키텍처 구현 및 운영
- PostgreSQL 성능 최적화 (파티셔닝, 인덱스 전략)
- 대용량 트랜잭션 처리 시스템의 안정성 확보 (SLA 99.9%)

[자격 요건]
- Python 백엔드 개발 경력 3년 이상
- Django 또는 FastAPI 실무 경험
- PostgreSQL 설계 및 쿼리 최적화 경험
- Redis를 활용한 캐싱·세션 관리 경험
- 대졸 이상

[우대 사항]
- Kafka 또는 메시지 브로커 운영 경험
- Kubernetes 환경에서의 서비스 운영 경험
- 핀테크/결제 도메인 경험
- 데이터를 기반으로 의사결정하고 팀을 설득하는 분
- 장애 상황에서 침착하게 원인을 분석하고 해결하는 분
"""

RESUME_MID_MATCH = """
[인적 사항]
이름: 박서준 | 연락처: 010-9876-5432 | 이메일: seojun@example.com

[학력]
- 서울과학기술대학교 소프트웨어공학과 학사 졸업 (2019.02)

[경력]
1. (주)빠른배달 — 백엔드 개발자 (2019.03 ~ 2022.02, 3년)
   - Python/Django 기반 배달 플랫폼 API 서버 개발 및 운영
   - 주문/결제 API 30개 이상 설계 및 구현
   - Redis 캐싱 도입: 주문 조회 API 응답 시간 1.2초 → 0.3초 (75% 개선)
   - PostgreSQL 쿼리 최적화: N+1 문제 해결, 인덱스 전략 수립
   - Celery + Redis 기반 비동기 알림 시스템 구축 (일 100만 건)

2. (주)핀브릿지 — 백엔드 개발자 (2022.03 ~ 현재, 2년)
   - FastAPI 기반 간편결제 API 서버 설계 및 운영
   - Kafka 도입: 결제 이벤트 처리 시스템 구축, 처리량 3배 향상
   - Kubernetes 환경에서 마이크로서비스 운영 (노드 8대)
   - PostgreSQL 파티셔닝 적용: 1억 건 트랜잭션 데이터 조회 성능 10배 향상
   - 장애 대응 온콜 담당, SLA 99.9% 유지

[기술 스택]
- 언어: Python (5년+), SQL
- 프레임워크: Django, FastAPI, Celery
- 데이터베이스: PostgreSQL, Redis, MySQL
- 메시지브로커: Kafka
- 인프라: Kubernetes, Docker, AWS (EC2/RDS/S3/SQS), Terraform (기초)
- 모니터링: Datadog, Grafana, Prometheus
"""

CL_MID_MATCH = """
[지원 동기]
결제·정산 도메인에서 5년간 쌓아온 경험을 핀크의 빠른 성장 환경에서 더 깊이 발전시키고 싶습니다.
특히 Kafka 기반 이벤트 아키텍처와 대용량 트랜잭션 처리라는 핵심 과제가
현재 제가 가장 몰두하고 있는 기술 영역과 정확히 일치해 지원했습니다.

[기술적 성취]
핀브릿지에서 일 평균 500만 건의 결제 이벤트를 처리하는 시스템을 담당했습니다.
초기에 단일 DB에 모든 트랜잭션을 동기 처리하던 구조에서 OOM이 반복 발생했을 때,
Kafka를 도입해 이벤트를 비동기로 분리하고 PostgreSQL 파티셔닝을 병행 적용해
처리량을 3배 끌어올리고 장애를 0건으로 줄인 경험이 있습니다.

[협업 방식]
의사결정 시 항상 측정 지표를 먼저 수집합니다.
Redis 캐싱 도입 당시 팀 내 "캐시 정합성 문제"에 대한 우려가 있었는데,
실제 캐시 히트율과 정합성 오류 발생 케이스를 직접 측정해 데이터로 설득한 뒤 도입했습니다.
결과적으로 6개월간 정합성 이슈 0건, 응답 속도 75% 개선이라는 성과를 냈습니다.
"""

# ─────────────────────────────────────────
# 시나리오 3: 경력 미스매치 — 도메인/기술 불일치
# ─────────────────────────────────────────

JD_PLATFORM_BACKEND = """
[회사명] 쇼핑라이브 (이커머스 플랫폼, 300인)
[직무명] 플랫폼 백엔드 개발자 (Java/Spring)
[고용 형태] 정규직

[담당 업무]
- Spring Boot 기반 이커머스 플랫폼 핵심 도메인 개발
- MSA 환경에서 도메인 서비스 간 통신 설계 (gRPC, REST)
- 대용량 상품/주문 데이터 처리 최적화
- JUnit5, Mockito 기반 단위·통합 테스트 작성

[자격 요건]
- Java, Spring Boot 실무 경험 3년 이상
- MySQL 설계 및 최적화 경험
- JPA/Hibernate 실무 경험
- 대졸 이상

[우대 사항]
- MSA 또는 분산 시스템 설계 경험
- Kafka 또는 RabbitMQ 경험
- 이커머스 도메인 경험
- 오너십을 갖고 서비스 품질을 개선하는 분
"""

RESUME_MISMATCH = """
[인적 사항]
이름: 최민수 | 이메일: minsu@example.com

[학력]
- 부산대학교 전기공학과 학사 졸업 (2018.02)

[경력]
1. (주)클라우드솔루션 — DevOps 엔지니어 (2018.03 ~ 2021.02, 3년)
   - AWS 인프라 설계 및 운영 (EC2, EKS, RDS, S3)
   - Terraform으로 인프라 코드화 (IaC)
   - Kubernetes 클러스터 운영 및 CI/CD 파이프라인 구축

2. (주)애드테크 — 백엔드 개발자 (2021.03 ~ 현재, 3년)
   - Python/Django 기반 광고 집행 API 서버 개발
   - MySQL 스키마 설계 및 대용량 로그 처리 (일 5억 건)
   - Redis 캐싱, Celery 비동기 처리 구현

[기술 스택]
- 언어: Python (6년), Bash, Go (기초)
- 프레임워크: Django, FastAPI
- 데이터베이스: MySQL, PostgreSQL, Redis
- 인프라: Kubernetes, Terraform, AWS, Docker
- 기타: Java (학부 수준, 실무 미사용)
"""

CL_MISMATCH = """
[지원 동기]
DevOps와 백엔드를 넘나든 경험을 바탕으로 이커머스 도메인에서 새로운 도전을 하고 싶습니다.
Java는 학부 시절 배운 이후 실무에서 사용하지 않았지만,
Python으로 유사한 OOP 패턴과 대용량 데이터 처리를 다뤄온 경험이 있어
Spring Boot 학습에 빠르게 적응할 자신이 있습니다.

[기술 역량]
애드테크에서 일 5억 건의 광고 로그를 처리하는 파이프라인을 설계했습니다.
MySQL 파티셔닝과 Redis 캐싱을 결합해 집계 쿼리 응답 시간을 8초에서 0.5초로 줄였습니다.
"""


# ══════════════════════════════════════════════════════════════
# 파이프라인 직접 실행 헬퍼 (DB 없음)
# ══════════════════════════════════════════════════════════════

def _run_pipeline(jd_text, resume_text, cl_text, job_role, company_name, career_level):
    """
    _run_analysis와 동일한 파이프라인을 DB 없이 서비스 함수로 직접 실행.
    반환값: views의 match/ 응답과 동일한 구조의 dict
    """
    # 1) JD 분석 + 이력서 분석 병렬 실행
    with ThreadPoolExecutor(max_workers=3) as executor:
        f_jd_kw  = executor.submit(extract_jd_keywords,    jd_text)
        f_jd_req = executor.submit(extract_jd_requirements, jd_text)
        f_resume = executor.submit(analyze_resume, resume_text, cl_text)
        jd_kw          = f_jd_kw.result()
        jd_req         = f_jd_req.result()
        resume_summary = f_resume.result()

    inferred_level = resume_summary.get("career_level", career_level)

    # 2) 매칭 점수 계산
    match_result = calculate_match_score(
        jd_keywords=jd_kw,
        resume_analysis=resume_summary,
        cover_letter_text=cl_text,
        career_level=inferred_level,
        jd_requirements=jd_req,
        job_role=job_role,
    )
    match_result = build_match_result(match_result, inferred_level)

    # 3) 갭 분석
    gap_result  = calculate_gap(
        jd_keywords=jd_kw,
        jd_requirements=jd_req,
        resume_analysis=resume_summary,
        unmatched_keywords=match_result["unmatched_keywords"],
        trait_details=match_result.get("trait_details"),
    )
    gap_message = build_gap_message(gap_result, inferred_level)

    # 4) 질문 생성
    raw_questions = generate_questions(
        job_role=job_role,
        company_name=company_name,
        jd_keywords=jd_kw,
        resume_analysis=resume_summary,
    )
    merged    = merge_and_deduplicate(raw_questions, jd_kw, resume_summary)
    with_star = generate_star_answers(merged, job_role, company_name, resume_summary)
    questions = build_question_output(with_star)

    return {
        "match_score":        match_result["match_score"],
        "tech_score":         match_result["tech_score"],
        "trait_score":        match_result["trait_score"],
        "matched_keywords":   match_result["matched_keywords"],
        "unmatched_keywords": match_result["unmatched_keywords"],
        "jd_keywords":        {**jd_kw, "requirements": jd_req},
        "resume_analysis":    resume_summary,
        "gap":                gap_result,
        "gap_message":        gap_message,
        "strengths":          match_result["strengths"],
        "weaknesses":         match_result["weaknesses"],
        "cl_points":          match_result["cl_points"],
        "questions":          questions,
    }


# ══════════════════════════════════════════════════════════════
# 시나리오 1: 신입 지원자
# ══════════════════════════════════════════════════════════════

class TestScenario신입(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = _run_pipeline(
            jd_text=JD_STARTUP_BACKEND,
            resume_text=RESUME_ENTRY_JUNIOR,
            cl_text=CL_ENTRY_JUNIOR,
            job_role="백엔드 개발자",
            company_name="커리어닷집",
            career_level="entry",
        )

    def test_전체_파이프라인_실행(self):
        print("\n" + "═" * 60)
        print("【시나리오 1: 신입 지원자】 전체 결과")
        print("═" * 60)
        pprint.pprint(self.result, width=100)
        print("═" * 60)
        self.assertIsInstance(self.result, dict)

    def test_점수_범위(self):
        score = self.result["match_score"]
        print(f"\n[신입] match_score={score}")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score,    100.0)

    def test_jd_keywords_구조(self):
        jd_kw = self.result["jd_keywords"]
        print(f"\n[신입] jd_keywords:")
        pprint.pprint(jd_kw)
        self.assertIn("tech_keywords",  jd_kw)
        self.assertIn("trait_keywords", jd_kw)
        self.assertIn("requirements",   jd_kw)
        self.assertGreater(len(jd_kw["tech_keywords"]),  0)
        self.assertGreater(len(jd_kw["trait_keywords"]), 0)

    def test_resume_analysis_신입_판별(self):
        ra = self.result["resume_analysis"]
        print(f"\n[신입] resume_analysis:")
        pprint.pprint(ra)
        self.assertEqual(ra["career_level"],        "entry")
        self.assertEqual(ra["years_of_experience"],  0)

    def test_gap_결과(self):
        print(f"\n[신입] gap:")
        pprint.pprint(self.result["gap"])
        print(f"[신입] gap_message:")
        pprint.pprint(self.result["gap_message"])
        self.assertIsInstance(self.result["gap"],         dict)
        self.assertIsInstance(self.result["gap_message"], dict)

    def test_strengths_weaknesses_cl_points(self):
        print(f"\n[신입] strengths:  {self.result['strengths']}")
        print(f"[신입] weaknesses: {self.result['weaknesses']}")
        print(f"[신입] cl_points:  {self.result['cl_points']}")
        self.assertIsInstance(self.result["strengths"],  list)
        self.assertIsInstance(self.result["weaknesses"], list)
        self.assertIsInstance(self.result["cl_points"],  list)

    def test_질문_생성(self):
        questions = self.result["questions"]
        print(f"\n[신입] 생성된 질문 {len(questions)}개:")
        for q in questions:
            print(f"  [{q['question_type']:12}] {q['question_text'][:60]}")
        self.assertGreater(len(questions), 0)

    def test_질문_STAR_구조(self):
        star_keys = {"summary", "situation", "task", "action", "result"}
        print(f"\n[신입] STAR 답변 샘플 (첫 번째 질문):")
        pprint.pprint(self.result["questions"][0])
        for q in self.result["questions"]:
            missing = star_keys - set(q["answer"].keys())
            self.assertFalse(missing,
                             f"STAR 필드 누락: {missing} — {q['question_text'][:30]}")


# ══════════════════════════════════════════════════════════════
# 시나리오 2: 경력 매칭 지원자
# ══════════════════════════════════════════════════════════════

class TestScenario경력_매칭(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = _run_pipeline(
            jd_text=JD_FINTECH_BACKEND,
            resume_text=RESUME_MID_MATCH,
            cl_text=CL_MID_MATCH,
            job_role="백엔드 개발자",
            company_name="핀크",
            career_level="experienced",
        )

    def test_전체_파이프라인_실행(self):
        print("\n" + "═" * 60)
        print("【시나리오 2: 경력 매칭 지원자】 전체 결과")
        print("═" * 60)
        pprint.pprint(self.result, width=100)
        print("═" * 60)
        self.assertIsInstance(self.result, dict)

    def test_점수_범위(self):
        score = self.result["match_score"]
        print(f"\n[경력매칭] match_score={score}")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score,    100.0)

    def test_career_level_experienced(self):
        ra = self.result["resume_analysis"]
        print(f"\n[경력매칭] resume_analysis:")
        pprint.pprint(ra)
        self.assertEqual(ra["career_level"], "experienced")
        self.assertGreaterEqual(ra["years_of_experience"], 3)

    def test_matched_keywords_포함(self):
        matched = self.result["matched_keywords"]
        print(f"\n[경력매칭] matched_keywords: {matched}")
        self.assertGreater(len(matched), 0, "매칭된 키워드가 없음")

    def test_strengths_weaknesses_내용(self):
        print(f"\n[경력매칭] strengths:")
        pprint.pprint(self.result["strengths"])
        print(f"[경력매칭] weaknesses:")
        pprint.pprint(self.result["weaknesses"])
        print(f"[경력매칭] cl_points:")
        pprint.pprint(self.result["cl_points"])
        self.assertGreater(len(self.result["strengths"]), 0)

    def test_질문_생성(self):
        questions = self.result["questions"]
        print(f"\n[경력매칭] 생성된 질문 {len(questions)}개:")
        for q in questions:
            print(f"  [{q['question_type']:12}] {q['question_text'][:60]}")
        self.assertGreater(len(questions), 0)


# ══════════════════════════════════════════════════════════════
# 시나리오 3: 경력 미스매치 지원자
# ══════════════════════════════════════════════════════════════

class TestScenario경력_미스매치(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = _run_pipeline(
            jd_text=JD_PLATFORM_BACKEND,
            resume_text=RESUME_MISMATCH,
            cl_text=CL_MISMATCH,
            job_role="플랫폼 백엔드 개발자",
            company_name="쇼핑라이브",
            career_level="experienced",
        )

    def test_전체_파이프라인_실행(self):
        print("\n" + "═" * 60)
        print("【시나리오 3: 경력 미스매치 지원자】 전체 결과")
        print("═" * 60)
        pprint.pprint(self.result, width=100)
        print("═" * 60)
        self.assertIsInstance(self.result, dict)

    def test_점수_범위(self):
        score = self.result["match_score"]
        print(f"\n[미스매치] match_score={score}")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score,    100.0)

    def test_unmatched_keywords_포함(self):
        unmatched = self.result["unmatched_keywords"]
        print(f"\n[미스매치] unmatched_keywords: {unmatched}")
        self.assertGreater(len(unmatched), 0, "미스매치인데 unmatched_keywords가 비어 있음")

    def test_gap_기술갭_포함(self):
        gap = self.result["gap"]
        print(f"\n[미스매치] gap:")
        pprint.pprint(gap)
        print(f"[미스매치] gap_message:")
        pprint.pprint(self.result["gap_message"])
        self.assertIn("tech_gap", gap)
        self.assertGreater(len(gap["tech_gap"]), 0, "기술 미스매치인데 tech_gap이 비어 있음")

    def test_weaknesses_미스매치_반영(self):
        print(f"\n[미스매치] weaknesses:")
        pprint.pprint(self.result["weaknesses"])
        self.assertGreater(len(self.result["weaknesses"]), 0)

    def test_질문_생성(self):
        questions = self.result["questions"]
        print(f"\n[미스매치] 생성된 질문 {len(questions)}개:")
        for q in questions:
            print(f"  [{q['question_type']:12}] {q['question_text'][:60]}")
        self.assertGreater(len(questions), 0)


# ══════════════════════════════════════════════════════════════
# 점수 비교 (시나리오 간 상대적 검증)
# ══════════════════════════════════════════════════════════════

class TestScenario점수비교(SimpleTestCase):
    """
    동일 JD에 대해 신입 vs 경력 매칭 점수를 비교한다.
    GPT 비결정성으로 항상 보장되진 않지만, 프롬프트 방향성 검증용.
    """

    def test_경력매칭이_신입보다_높은_점수(self):
        entry_result = _run_pipeline(
            jd_text=JD_FINTECH_BACKEND,
            resume_text=RESUME_ENTRY_JUNIOR,
            cl_text=CL_ENTRY_JUNIOR,
            job_role="백엔드 개발자",
            company_name="핀크",
            career_level="entry",
        )
        mid_result = _run_pipeline(
            jd_text=JD_FINTECH_BACKEND,
            resume_text=RESUME_MID_MATCH,
            cl_text=CL_MID_MATCH,
            job_role="백엔드 개발자",
            company_name="핀크",
            career_level="experienced",
        )
        score_entry = entry_result["match_score"]
        score_mid   = mid_result["match_score"]
        print(f"\n[점수 비교] 신입={score_entry:.1f}  경력매칭={score_mid:.1f}")

        self.assertGreater(score_mid, score_entry,
                           f"경력 매칭({score_mid:.1f})이 신입({score_entry:.1f})보다 낮음")
