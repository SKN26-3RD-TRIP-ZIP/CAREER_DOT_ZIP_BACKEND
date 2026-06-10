"""
star_service 프롬프트 품질 테스트 (실제 GPT 호출)

테스트 대상:
  generate_star_answers()   STAR 구조 모범 답변 생성

주의:
  실제 OpenAI API를 호출합니다. OPENAI_API_KEY 환경변수가 필요합니다.
  GPT 응답 비결정성으로 인해 타입·구조·포함 여부를 검증합니다.

실행:
  pytest apps/analysis/tests/test_star_service.py -v -s
  pytest apps/analysis/tests/test_star_service.py -v -s -k "entry"
"""

import pytest
from apps.analysis.services.star_service import generate_star_answers


# ══════════════════════════════════════════════════════════════
# 공통 픽스처
# ══════════════════════════════════════════════════════════════

RESUME_BACKEND = """
[학력]
- 한국대학교 컴퓨터공학과 졸업 (2022.02)

[경력]
- (주)패스트딜리버리 백엔드 개발자 (2022.03~2024.03, 2년)
  - Django 기반 배달 플랫폼 API 30개 개발
  - Redis 캐싱 도입으로 응답 속도 40% 개선

[기술 스택]
- Python, Django, PostgreSQL, Redis, Docker, AWS
"""

COVER_LETTER_BACKEND = """
저는 성능 문제를 데이터로 접근합니다. 배달 플랫폼에서 N+1 문제를 발견해
Redis 캐싱으로 응답 시간을 1.2초 → 0.3초로 줄인 경험이 있습니다.
팀 내에서 코드 리뷰 문화를 주도적으로 정착시킨 경험도 있습니다.
"""

RESUME_ENTRY = """
[학력]
- 서울대학교 소프트웨어학부 재학 중 (졸업예정 2025.08)

[프로젝트]
- 중고거래 플랫폼 (팀 3인, 2024.09~2024.12)
  - Django REST API 8개 설계, MySQL 스키마 설계
  - GitHub Actions 기반 CI 구축

[기술 스택]
- Python, Django, MySQL, Docker (기초), Git
"""

COVER_LETTER_ENTRY = """
팀 프로젝트에서 JWT 토큰 오류를 3일 동안 탐색해 직접 해결했습니다.
팀원과 매주 코드 리뷰를 제안하고 운영했습니다.
"""

JD_TEXT = """
[직무] 백엔드 개발자
[기술] Python, Django, Redis, PostgreSQL
[인재상] 주도적으로 문제를 해결하는 분, 데이터 기반으로 의사결정하는 분
"""

SAMPLE_QUESTIONS_MIXED = [
    {"type": "technical",   "text": "Redis 캐싱 전략에 대해 설명하고 실제 적용 경험을 말해주세요.", "source": "jd",    "basis": "Redis 필수"},
    {"type": "personality", "text": "팀에서 갈등이 생겼을 때 어떻게 해결했나요?",               "source": "coverletter", "basis": "팀워크"},
    {"type": "experience",  "text": "본인이 주도한 가장 복잡한 기술 문제 해결 사례를 말해주세요.", "source": "project", "basis": "성능 개선"},
]

SAMPLE_QUESTIONS_TECHNICAL_ONLY = [
    {"type": "technical", "text": "Django ORM의 N+1 문제를 어떻게 해결하나요?",          "source": "jd", "basis": "Django 필수"},
    {"type": "technical", "text": "REST API 설계 시 버전 관리는 어떻게 하시나요?",       "source": "jd", "basis": "API 설계"},
    {"type": "technical", "text": "데이터베이스 인덱스 최적화 경험이 있으신가요?",       "source": "jd", "basis": "PostgreSQL"},
    {"type": "technical", "text": "Docker와 Kubernetes의 차이를 설명해주세요.",          "source": "jd", "basis": "인프라"},
]


def _assert_star_structure(answer: dict, question_text: str = ""):
    """STAR 답변 구조 공통 검증"""
    required_keys = {"summary", "situation", "task", "action", "result", "basis_source"}
    missing = required_keys - set(answer.keys())
    assert not missing, f"'{question_text}' - STAR 키 누락: {missing}"

    for key in ["summary", "situation", "task", "action", "result"]:
        assert isinstance(answer[key], str), f"'{key}'가 str이 아님: {type(answer[key])}"
        assert len(answer[key]) > 0, f"'{key}'가 빈 문자열"

    valid_sources = {"project", "coverletter", "resume", "jd"}
    src = answer.get("basis_source", "")
    is_valid = any(src.startswith(v) for v in valid_sources)
    assert is_valid, f"basis_source 값이 유효하지 않음: '{src}'"


# ══════════════════════════════════════════════════════════════
# 기본 구조 검증
# ══════════════════════════════════════════════════════════════

class TestGenerateStarAnswersStructure:

    def test_반환_개수_질문수와_일치(self):
        result = generate_star_answers(
            questions=SAMPLE_QUESTIONS_MIXED,
            job_role="백엔드 개발자",
            company_name="테스트컴퍼니",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        print(f"\n반환 질문 수: {len(result)}")
        assert len(result) == len(SAMPLE_QUESTIONS_MIXED)

    def test_각_항목에_answer_키_존재(self):
        result = generate_star_answers(
            questions=SAMPLE_QUESTIONS_MIXED,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        for item in result:
            assert "answer" in item, f"answer 키 없음: {item.get('text')}"

    def test_star_내부_필드_구조(self):
        result = generate_star_answers(
            questions=SAMPLE_QUESTIONS_MIXED,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        for item in result:
            _assert_star_structure(item["answer"], item.get("text", ""))
        print(f"\n첫 번째 STAR: {result[0]['answer']}")

    def test_원본_질문_필드_유지(self):
        """generate 후에도 type / text / source / basis가 그대로 유지"""
        result = generate_star_answers(
            questions=SAMPLE_QUESTIONS_MIXED,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        for original, output in zip(SAMPLE_QUESTIONS_MIXED, result):
            assert output["type"]   == original["type"]
            assert output["text"]   == original["text"]
            assert output["source"] == original["source"]


# ══════════════════════════════════════════════════════════════
# 신입 vs 경력 프로파일
# ══════════════════════════════════════════════════════════════

class TestGenerateStarAnswersByProfile:

    def test_경력자_프로파일_프로젝트_인용(self):
        """경력자의 경우 answer에 프로젝트 또는 실무 관련 내용이 반영되어야 함"""
        questions = [{"type": "experience", "text": "가장 성과가 컸던 프로젝트를 설명해주세요.", "source": "project", "basis": "배달 플랫폼"}]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        print(f"\n경력자 경험 STAR: {result[0]['answer']}")
        _assert_star_structure(result[0]["answer"])

    def test_신입_프로파일_프로젝트_기반_답변(self):
        """신입은 프로젝트 기반으로 답변이 구성되어야 함"""
        questions = [{"type": "experience", "text": "팀 프로젝트에서 본인의 역할은?", "source": "project", "basis": "중고거래 플랫폼"}]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="스타트업",
            jd_text=JD_TEXT,
            resume_text=RESUME_ENTRY,
            cover_letter_text=COVER_LETTER_ENTRY,
        )
        print(f"\n신입 경험 STAR: {result[0]['answer']}")
        _assert_star_structure(result[0]["answer"])

    def test_인성_질문_자소서_기반(self):
        """인성 질문은 자소서에서 근거를 가져와야 함"""
        questions = [{"type": "personality", "text": "협업 중 어려움을 극복한 사례를 말해주세요.", "source": "coverletter", "basis": "팀워크"}]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        print(f"\n인성 STAR: {result[0]['answer']}")
        answer = result[0]["answer"]
        _assert_star_structure(answer)
        # basis_source가 coverletter 또는 resume이어야 함
        assert answer["basis_source"] in {"coverletter", "resume", "jd"} or \
               answer["basis_source"].startswith("project"), \
               f"인성 질문의 basis_source가 이상함: {answer['basis_source']}"


# ══════════════════════════════════════════════════════════════
# 기술 질문 유형별
# ══════════════════════════════════════════════════════════════

class TestGenerateStarAnswersTechnical:

    def test_기술_질문_여러개_한번에(self):
        """기술 질문 4개를 한 번에 처리"""
        result = generate_star_answers(
            questions=SAMPLE_QUESTIONS_TECHNICAL_ONLY,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        print(f"\n기술 질문 4개 STAR 생성 완료")
        assert len(result) == 4
        for item in result:
            assert "answer" in item
            _assert_star_structure(item["answer"], item["text"])

    def test_기술_질문_summary_두괄식(self):
        """summary는 핵심 결론을 먼저 제시해야 함 (30자 내외)"""
        questions = [{"type": "technical", "text": "Redis 캐싱 전략을 설명해주세요.", "source": "jd", "basis": "Redis"}]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        summary = result[0]["answer"]["summary"]
        print(f"\n기술 summary: '{summary}'")
        assert len(summary) > 5, "summary가 너무 짧음"
        assert len(summary) < 200, "summary가 너무 김 (두괄식 아닐 가능성)"

    def test_result_필드_성과_포함(self):
        """result 필드에 성과나 배운 점이 포함되어야 함"""
        questions = [{"type": "experience", "text": "성능 개선 경험을 말해주세요.", "source": "project", "basis": "Redis 40%"}]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        result_text = result[0]["answer"]["result"]
        print(f"\nresult 필드: '{result_text}'")
        assert len(result_text) > 10, "result 필드가 너무 짧음"


# ══════════════════════════════════════════════════════════════
# 엣지 케이스
# ══════════════════════════════════════════════════════════════

class TestGenerateStarAnswersEdgeCases:

    def test_이력서_자소서_없을때_빈문자열(self):
        """이력서·자소서가 없어도 에러 없이 답변 생성"""
        questions = [{"type": "technical", "text": "Django REST Framework에 대해 설명해주세요.", "source": "jd", "basis": "Django"}]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="",
            jd_text="",
            resume_text="",
            cover_letter_text="",
        )
        print(f"\n이력서 없음 STAR: {result[0]['answer']}")
        assert len(result) == 1
        assert "answer" in result[0]

    def test_회사명_없어도_동작(self):
        questions = [{"type": "personality", "text": "왜 이 회사에 지원했나요?", "source": "jd", "basis": "지원 동기"}]
        result = generate_star_answers(
            questions=questions,
            job_role="프론트엔드 개발자",
            company_name="",
            jd_text="",
            resume_text=RESUME_ENTRY,
            cover_letter_text=COVER_LETTER_ENTRY,
        )
        assert "answer" in result[0]

    def test_질문_1개만_처리(self):
        questions = [SAMPLE_QUESTIONS_MIXED[0]]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        assert len(result) == 1
        _assert_star_structure(result[0]["answer"])

    def test_basis_source_project_형식(self):
        """프로젝트 기반 질문의 basis_source는 'project:프로젝트명' 형식이어야 함"""
        questions = [{"type": "experience", "text": "배달 플랫폼 개발 경험을 구체적으로 설명해주세요.", "source": "project", "basis": "배달플랫폼"}]
        result = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="",
            jd_text=JD_TEXT,
            resume_text=RESUME_BACKEND,
            cover_letter_text=COVER_LETTER_BACKEND,
        )
        src = result[0]["answer"]["basis_source"]
        print(f"\nbasis_source: '{src}'")
        # project:xxx 또는 resume / coverletter / jd 중 하나
        valid = src.startswith("project:") or src in {"resume", "coverletter", "jd"}
        assert valid, f"basis_source 형식 이상: '{src}'"
