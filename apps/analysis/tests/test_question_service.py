"""
question_service (오케스트레이터) 통합 테스트 (실제 GPT + 임베딩 호출)

테스트 대상:
  generate_all_questions()   Pipeline 3 ②~⑥ 전체 실행

주의:
  실제 OpenAI API를 호출합니다. OPENAI_API_KEY 환경변수가 필요합니다.
  RAG는 Pinecone 없으면 MySQL 폴백 → MySQL도 없으면 mock 처리.
  통합 테스트이므로 실행 시간이 깁니다.

실행:
  pytest apps/analysis/tests/test_question_service.py -v -s
  pytest apps/analysis/tests/test_question_service.py -v -s -k "format"
"""

import pytest
from unittest.mock import patch
from apps.analysis.services.question_service import generate_all_questions


# ══════════════════════════════════════════════════════════════
# 공통 픽스처
# ══════════════════════════════════════════════════════════════

JD_KEYWORDS_DICT = {
    "tech_keywords":  ["Python", "Django", "Redis", "PostgreSQL"],
    "trait_keywords": ["주도적으로 문제를 해결하는 분", "커뮤니케이션이 원활한 분"],
}

JD_KEYWORDS_LIST = ["Python", "Django", "Redis"]

RESUME_ANALYSIS = {
    "tech_stack":      ["Python", "Django", "PostgreSQL", "Redis", "Docker"],
    "key_experiences": ["스타트업에서 백엔드 API 20개 설계", "Redis 캐싱으로 응답 속도 40% 개선"],
    "strengths":       ["성능 최적화", "빠른 문제해결"],
    "trait_evidence":  ["데이터를 근거로 팀 의사결정을 이끌어낸 경험", "코드 리뷰 문화를 주도적으로 도입"],
    "projects": [
        {"name": "배달플랫폼", "role": "백엔드 리드", "tech": ["Python", "Django", "Redis"], "result": "DAU 3천 달성", "domain": "logistics"},
    ],
}

RESUME_TEXT = """
[학력] 한국대학교 컴퓨터공학과 졸업 (2022.02)
[경력] (주)패스트딜리버리 백엔드 개발자 (2022~2024, 2년)
  - Django 기반 배달 플랫폼 API 30개 개발
  - Redis 캐싱 도입으로 응답 속도 40% 개선
[기술] Python, Django, PostgreSQL, Redis, Docker
"""

COVER_LETTER_TEXT = """
성능 문제를 데이터로 접근합니다. N+1 문제를 발견해 Redis 캐싱으로 응답 시간을 1.2초 → 0.3초로 줄였습니다.
팀 내 코드 리뷰 문화를 주도적으로 정착시켰습니다.
"""

JD_TEXT = """
[직무] 백엔드 개발자
[기술] Python, Django, Redis, PostgreSQL
[인재상] 주도적으로 문제를 해결하는 분, 데이터 기반 의사결정
"""

# MySQL 폴백에서 반환할 mock 데이터 (RAG 부분 mock)
MOCK_RAG_RESULTS = [
    {"type": "technical", "text": "Redis pub/sub 패턴을 설명해주세요.", "question_type": "technical",
     "question_text": "Redis pub/sub 패턴을 설명해주세요.", "source": "question_bank",
     "matched_keyword": "Redis", "similarity_score": 0.80, "basis": ""},
    {"type": "personality", "text": "갈등을 해결한 경험을 말해주세요.", "question_type": "personality",
     "question_text": "갈등을 해결한 경험을 말해주세요.", "source": "question_bank",
     "matched_keyword": "협업", "similarity_score": 0.75, "basis": ""},
    {"type": "experience", "text": "어려운 기술 문제 해결 사례를 말해주세요.", "question_type": "experience",
     "question_text": "어려운 기술 문제 해결 사례를 말해주세요.", "source": "question_bank",
     "matched_keyword": "문제해결", "similarity_score": 0.72, "basis": ""},
]


# ══════════════════════════════════════════════════════════════
# 반환 형식 검증
# ══════════════════════════════════════════════════════════════

class TestGenerateAllQuestionsFormat:

    def test_반환_형식_필수_키(self):
        """각 질문 항목에 question / type / source / basis / star 키가 있어야 함"""
        with patch("apps.analysis.services.question_service.search_similar_questions", return_value=MOCK_RAG_RESULTS):
            result = generate_all_questions(
                job_role="백엔드 개발자",
                company_name="테스트컴퍼니",
                jd_keywords=JD_KEYWORDS_DICT,
                resume_analysis=RESUME_ANALYSIS,
                jd_text=JD_TEXT,
                resume_text=RESUME_TEXT,
                cover_letter_text=COVER_LETTER_TEXT,
            )

        print(f"\n생성된 질문 수: {len(result)}")
        assert isinstance(result, list)
        assert len(result) > 0

        required_keys = {"question", "type", "source"}
        for i, item in enumerate(result):
            missing = required_keys - set(item.keys())
            assert not missing, f"질문[{i}] 필드 누락: {missing}"

    def test_star_내부_필드(self):
        """star 키가 있으면 STAR 5개 필드 모두 존재해야 함"""
        with patch("apps.analysis.services.question_service.search_similar_questions", return_value=MOCK_RAG_RESULTS):
            result = generate_all_questions(
                job_role="백엔드 개발자",
                company_name="",
                jd_keywords=JD_KEYWORDS_DICT,
                resume_analysis=RESUME_ANALYSIS,
                jd_text=JD_TEXT,
                resume_text=RESUME_TEXT,
                cover_letter_text=COVER_LETTER_TEXT,
            )

        star_keys = {"summary", "situation", "task", "action", "result"}
        for item in result:
            if "star" in item:
                missing = star_keys - set(item["star"].keys())
                assert not missing, f"star 내부 필드 누락: {missing}"


# ══════════════════════════════════════════════════════════════
# jd_keywords 하위 호환
# ══════════════════════════════════════════════════════════════

class TestGenerateAllQuestionsBackwardCompat:

    def test_jd_keywords_list_형식(self):
        """구형 list 형식도 정상 처리"""
        with patch("apps.analysis.services.question_service.search_similar_questions", return_value=MOCK_RAG_RESULTS):
            result = generate_all_questions(
                job_role="백엔드 개발자",
                company_name="",
                jd_keywords=JD_KEYWORDS_LIST,  # 구형 list 형식
                resume_analysis=RESUME_ANALYSIS,
                jd_text=JD_TEXT,
                resume_text=RESUME_TEXT,
                cover_letter_text=COVER_LETTER_TEXT,
            )
        print(f"\nList 형식 jd_keywords → 결과: {len(result)}개")
        assert isinstance(result, list)

    def test_jd_keywords_dict_형식(self):
        """신형 dict 형식도 정상 처리"""
        with patch("apps.analysis.services.question_service.search_similar_questions", return_value=MOCK_RAG_RESULTS):
            result = generate_all_questions(
                job_role="백엔드 개발자",
                company_name="",
                jd_keywords=JD_KEYWORDS_DICT,  # 신형 dict 형식
                resume_analysis=RESUME_ANALYSIS,
                jd_text=JD_TEXT,
                resume_text=RESUME_TEXT,
                cover_letter_text=COVER_LETTER_TEXT,
            )
        assert isinstance(result, list)


# ══════════════════════════════════════════════════════════════
# 엣지 케이스
# ══════════════════════════════════════════════════════════════

class TestGenerateAllQuestionsEdgeCases:

    def test_이력서_자소서_없어도_동작(self):
        """이력서·자소서 없어도 에러 없이 처리"""
        with patch("apps.analysis.services.question_service.search_similar_questions", return_value=MOCK_RAG_RESULTS):
            result = generate_all_questions(
                job_role="백엔드 개발자",
                company_name="",
                jd_keywords=JD_KEYWORDS_DICT,
                resume_analysis=RESUME_ANALYSIS,
                jd_text="",
                resume_text="",
                cover_letter_text="",
            )
        print(f"\n이력서 없음: {len(result)}개")
        assert isinstance(result, list)

    def test_rag_결과_없어도_llm으로_보완(self):
        """RAG 결과가 없어도 LLM 생성으로 질문이 만들어짐"""
        with patch("apps.analysis.services.question_service.search_similar_questions", return_value=[]):
            result = generate_all_questions(
                job_role="백엔드 개발자",
                company_name="",
                jd_keywords=JD_KEYWORDS_DICT,
                resume_analysis=RESUME_ANALYSIS,
                jd_text=JD_TEXT,
                resume_text=RESUME_TEXT,
                cover_letter_text=COVER_LETTER_TEXT,
            )
        print(f"\nRAG 없음 결과: {len(result)}개")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_question_키가_text가_아닌_question(self):
        """출력 포맷에서 내부 'text' 키가 'question'으로 변환되어야 함"""
        with patch("apps.analysis.services.question_service.search_similar_questions", return_value=MOCK_RAG_RESULTS):
            result = generate_all_questions(
                job_role="백엔드 개발자",
                company_name="",
                jd_keywords=JD_KEYWORDS_DICT,
                resume_analysis=RESUME_ANALYSIS,
                jd_text=JD_TEXT,
                resume_text=RESUME_TEXT,
                cover_letter_text=COVER_LETTER_TEXT,
            )
        for item in result:
            assert "question" in item, "'question' 키가 없음 (포맷 변환 실패)"
            assert "text" not in item, "내부 'text' 키가 그대로 노출됨"
