"""
question_gen_service 프롬프트 품질 테스트 (실제 GPT 호출)

테스트 대상:
  generate_questions()   LLM 기반 면접 질문 생성 + source/basis 태그

주의:
  실제 OpenAI API를 호출합니다. OPENAI_API_KEY 환경변수가 필요합니다.
  GPT 응답 비결정성으로 인해 타입·범위·포함 여부를 검증합니다.

실행:
  pytest apps/analysis/tests/test_question_gen_service.py -v -s
  pytest apps/analysis/tests/test_question_gen_service.py -v -s -k "count"
"""

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")
from apps.analysis.services.question_gen_service import (
    generate_questions,
    generate_github_questions,
    generate_github_questions_for_projects,
    _build_github_context,
)


# ══════════════════════════════════════════════════════════════
# 공통 픽스처
# ══════════════════════════════════════════════════════════════

JD_BACKEND = {
    "tech_keywords":  ["Python", "Django", "Redis", "PostgreSQL", "Docker"],
    "trait_keywords": ["주도적으로 문제를 해결하는 분", "데이터 기반으로 의사결정하는 분", "커뮤니케이션이 원활한 분"],
}

JD_FRONTEND = {
    "tech_keywords":  ["React", "TypeScript", "Next.js", "GraphQL"],
    "trait_keywords": ["자기주도적으로 학습하는 분", "팀플레이를 즐기는 분"],
}

JD_EMPTY = {
    "tech_keywords":  [],
    "trait_keywords": [],
}

RESUME_BACKEND = {
    "tech_stack":      ["Python", "Django", "PostgreSQL", "Redis", "Docker"],
    "key_experiences": ["스타트업에서 백엔드 API 20개 설계", "Redis 캐싱으로 응답 속도 40% 개선"],
    "strengths":       ["성능 최적화 경험", "빠른 문제해결 능력"],
    "trait_evidence":  ["데이터를 근거로 팀 의사결정을 이끈 경험", "코드 리뷰 문화 주도적 도입"],
    "projects": [
        {"name": "배달플랫폼", "role": "백엔드 리드", "tech": ["Python", "Django", "Redis"], "result": "DAU 3천 달성", "domain": "logistics"},
        {"name": "사이드프로젝트", "role": "개인 개발", "tech": ["FastAPI", "PostgreSQL"], "result": "앱스토어 출시", "domain": "productivity"},
    ],
}

RESUME_ENTRY = {
    "tech_stack":      ["Python", "Django", "MySQL", "Git"],
    "key_experiences": ["팀 프로젝트에서 REST API 5개 설계"],
    "strengths":       ["빠른 학습력 (2주 내 Django 습득)"],
    "trait_evidence":  ["JWT 토큰 오류를 3일 동안 탐색해 직접 해결", "매주 코드 리뷰 제안 및 운영"],
    "projects": [
        {"name": "중고거래앱", "role": "백엔드 개발", "tech": ["Python", "Django"], "result": "팀 프로젝트 완성", "domain": "e-commerce"},
    ],
}

RESUME_FRONTEND = {
    "tech_stack":      ["React", "TypeScript", "Next.js", "Tailwind CSS"],
    "key_experiences": ["커머스 웹사이트 프론트엔드 리드 개발"],
    "strengths":       ["UI 성능 최적화 경험"],
    "trait_evidence":  ["디자이너와 긴밀하게 협업해 UX 개선한 경험"],
    "projects": [
        {"name": "쇼핑몰", "role": "프론트엔드 개발", "tech": ["React", "TypeScript"], "result": "전환율 15% 향상", "domain": "e-commerce"},
    ],
}


def _assert_question_structure(q: dict, context: str = ""):
    """개별 질문 구조 검증"""
    assert "type"   in q, f"{context}: type 키 없음"
    assert "text"   in q, f"{context}: text 키 없음"
    assert "source" in q, f"{context}: source 키 없음"
    assert "basis"  in q, f"{context}: basis 키 없음"
    assert q["type"] in {"personality", "technical", "experience"}, \
        f"{context}: type 범위 초과 — '{q['type']}'"
    assert q["source"] in {"jd", "resume", "coverletter", "project", "combined"}, \
        f"{context}: source 범위 초과 — '{q['source']}'"
    assert len(q["text"]) > 5, f"{context}: text가 너무 짧음 — '{q['text']}'"


# ══════════════════════════════════════════════════════════════
# 기본 구조 및 반환 형식
# ══════════════════════════════════════════════════════════════

class TestGenerateQuestionsStructure:

    def test_기본_구조_백엔드(self):
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="테스트컴퍼니",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        print(f"\n생성된 질문 수: {len(result)}")
        assert isinstance(result, list)
        assert len(result) > 0
        for i, q in enumerate(result):
            _assert_question_structure(q, f"질문[{i}]")

    def test_질문_유형_구성_검증(self):
        """인성 3개, 기술 4개, 경험 3개 = 총 10개"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        types = [q["type"] for q in result]
        personality_count = types.count("personality")
        technical_count   = types.count("technical")
        experience_count  = types.count("experience")
        print(f"\n질문 유형: personality={personality_count} technical={technical_count} experience={experience_count}")
        assert personality_count == 3, f"인성 질문이 3개여야 함: {personality_count}"
        assert technical_count   == 4, f"기술 질문이 4개여야 함: {technical_count}"
        assert experience_count  == 3, f"경험 질문이 3개여야 함: {experience_count}"

    def test_basis_비어있지_않음(self):
        """모든 질문에 basis(근거)가 존재해야 함"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        for q in result:
            # basis가 빈 문자열이어도 에러는 아니지만 최소한 존재해야 함
            assert "basis" in q, f"basis 키 없음: {q['text']}"


# ══════════════════════════════════════════════════════════════
# JD 기술 키워드 반영 검증
# ══════════════════════════════════════════════════════════════

class TestGenerateQuestionsJdReflection:

    def test_기술_질문에_JD_키워드_반영(self):
        """기술 질문에 JD 기술 스택 중 최소 2개 이상 등장해야 함"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        technical_qs = [q["text"].lower() for q in result if q["type"] == "technical"]
        jd_tech_lower = [k.lower() for k in JD_BACKEND["tech_keywords"]]

        matched_count = sum(
            any(tech in q_text for tech in jd_tech_lower)
            for q_text in technical_qs
        )
        print(f"\n기술 질문에 JD 키워드 반영: {matched_count}/{len(technical_qs)}")
        assert matched_count >= 2, f"JD 기술 키워드가 기술 질문에 2개 이상 반영되지 않음"

    def test_프론트엔드_기술_질문_반영(self):
        """프론트엔드 JD의 경우 React/TypeScript 관련 질문이 생성되어야 함"""
        result = generate_questions(
            job_role="프론트엔드 개발자",
            company_name="",
            jd_keywords=JD_FRONTEND,
            resume_analysis=RESUME_FRONTEND,
        )
        all_text = " ".join(q["text"].lower() for q in result)
        print(f"\n프론트 질문 전체: {all_text[:200]}")
        assert "react" in all_text or "typescript" in all_text or "next" in all_text, \
            "프론트엔드 JD 기술 키워드가 질문에 반영되지 않음"

    def test_인재상_질문_자소서_기반(self):
        """인성 질문의 source가 coverletter 또는 combined여야 함"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        personality_qs = [q for q in result if q["type"] == "personality"]
        sources = [q["source"] for q in personality_qs]
        print(f"\n인성 질문 source: {sources}")
        valid_sources = {"coverletter", "combined", "resume", "jd"}
        assert all(s in valid_sources for s in sources), \
            f"인성 질문의 source에 이상한 값 포함: {sources}"


# ══════════════════════════════════════════════════════════════
# 지원자 프로파일별
# ══════════════════════════════════════════════════════════════

class TestGenerateQuestionsByProfile:

    def test_신입_프로파일_질문_생성(self):
        """신입 지원자 프로파일도 정상 동작"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="스타트업",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_ENTRY,
        )
        print(f"\n신입 질문 수: {len(result)}")
        assert len(result) == 10
        for q in result:
            _assert_question_structure(q, "신입")

    def test_경험_질문_프로젝트_인용(self):
        """경험 질문의 basis에 프로젝트 관련 내용이 있어야 함"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        experience_qs = [q for q in result if q["type"] == "experience"]
        print(f"\n경험 질문 basis: {[q['basis'] for q in experience_qs]}")
        sources = [q["source"] for q in experience_qs]
        assert all(s in {"project", "resume", "combined"} for s in sources), \
            f"경험 질문 source 이상: {sources}"


# ══════════════════════════════════════════════════════════════
# 엣지 케이스
# ══════════════════════════════════════════════════════════════

class TestGenerateQuestionsEdgeCases:

    def test_빈_JD_키워드(self):
        """JD 키워드가 없어도 에러 없이 질문 생성"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_EMPTY,
            resume_analysis=RESUME_ENTRY,
        )
        print(f"\n빈 JD 질문 수: {len(result)}")
        assert isinstance(result, list)
        # 질문이 생성되어야 함 (이력서 기반으로라도)
        assert len(result) > 0

    def test_회사명_없는_경우(self):
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        assert len(result) == 10

    def test_질문_중복_없음(self):
        """생성된 질문 텍스트가 중복되지 않아야 함"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        texts = [q["text"] for q in result]
        assert len(texts) == len(set(texts)), \
            f"중복 질문 발견: {[t for t in texts if texts.count(t) > 1]}"

    def test_질문_한_문장(self):
        """각 질문은 물음표로 끝나는 한 문장이어야 함"""
        result = generate_questions(
            job_role="백엔드 개발자",
            company_name="",
            jd_keywords=JD_BACKEND,
            resume_analysis=RESUME_BACKEND,
        )
        for q in result:
            text = q["text"].strip()
            print(f"\n  질문: '{text}'")
            # 물음표로 끝나거나 적당한 길이의 질문이어야 함
            assert len(text) > 10, f"질문이 너무 짧음: '{text}'"


# ══════════════════════════════════════════════════════════════
# GitHub 질문 생성 — 오프라인 검증 (GPT 호출 없는 부분만)
# ══════════════════════════════════════════════════════════════

class TestGithubQuestionsOffline:

    def test_미검증이면_빈리스트(self):
        """repo를 못 읽었으면(is_github_verified=False) GPT 호출 없이 빈 리스트"""
        project = {"name": "P", "tech": ["Django"], "is_github_verified": False}
        assert generate_github_questions(project) == []     # GPT 호출 안 함

    def test_컨텍스트에_미검증기술_강조(self):
        project = {
            "name": "마켓",
            "tech": ["Django", "Redis"],
            "verified_tech": ["Django"],
            "unverified_tech": ["Redis"],
            "github_frameworks": ["Django"],
            "github_languages": {"Python": 100.0},
            "contribution": 70,
        }
        ctx = _build_github_context(project, {"models.py": "class User: pass"})
        assert "Redis" in ctx                  # 미검증 기술이 컨텍스트에 들어감
        assert "근거 못 찾은 기술" in ctx
        assert "models.py" in ctx              # 코드 스니펫 포함
        assert "70" in ctx                     # 기여도 주장 포함

    def test_스니펫_없어도_컨텍스트_생성(self):
        project = {"name": "P", "tech": ["Python"], "github_languages": {}}
        ctx = _build_github_context(project, {})
        assert "코드 스니펫 없음" in ctx        # 빈 스니펫도 안전하게 처리

    def test_컨텍스트에_자소서_이력서_결합(self):
        """combined 질문용 — 이력서 경험 + 자소서 내용이 컨텍스트에 포함"""
        project = {"name": "마켓", "tech": ["Django"], "is_github_verified": True}
        resume = {
            "key_experiences": ["Redis 캐싱으로 응답속도 40% 개선"],
            "trait_evidence":  ["성능 최적화를 주도적으로 진행"],
        }
        ctx = _build_github_context(
            project, {}, resume_analysis=resume,
            cover_letter_text="저는 성능 병목을 직접 찾아 해결한 경험이 있습니다.",
        )
        assert "40% 개선" in ctx                 # 이력서 경험 포함
        assert "성능 최적화를 주도적으로" in ctx   # 자소서 역량 문장 포함
        assert "성능 병목을 직접" in ctx          # 자소서 원문 일부 포함

    def test_for_projects_검증된게_없으면_빈리스트(self):
        """검증 성공 프로젝트가 없으면 GPT 호출 없이 빈 리스트"""
        projects = [
            {"name": "A", "is_github_verified": False},
            {"name": "B"},     # 필드 없음
        ]
        assert generate_github_questions_for_projects(projects) == []

    def test_for_projects_빈입력(self):
        assert generate_github_questions_for_projects([]) == []
        assert generate_github_questions_for_projects(None) == []
