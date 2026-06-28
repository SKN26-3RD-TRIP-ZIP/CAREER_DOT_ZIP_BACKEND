"""
question_rag_service 단위 테스트 (Pinecone / MySQL 모킹)

테스트 대상:
  search_similar_questions()   Pinecone 검색 (MySQL 폴백 포함)

모킹 전략:
  - Pinecone 미설정 → _mysql_fallback 경로 테스트
  - _mysql_fallback을 mock해 DB 없이 테스트
  - Pinecone 설정 있을 때 → _pinecone_search 경로 mock

실행:
  pytest apps/analysis/tests/test_question_rag_service.py -v -s
"""

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")
from unittest.mock import patch, MagicMock
from apps.analysis.services.question_rag_service import search_similar_questions


JD_KEYWORDS_BACKEND = {
    "tech_keywords":  ["Python", "Django", "Redis"],
    "trait_keywords": ["주도적으로 문제를 해결하는 분"],
}

JD_KEYWORDS_EMPTY = {
    "tech_keywords":  [],
    "trait_keywords": [],
}

MOCK_DB_CANDIDATES = [
    {
        "question_bank_id": "uuid-001",
        "question_text":    "Redis 캐싱 전략에 대해 설명해주세요.",
        "question_type":    "technical",
        "match_score":      0.85,
    },
    {
        "question_bank_id": "uuid-002",
        "question_text":    "Django ORM의 N+1 문제를 어떻게 해결하나요?",
        "question_type":    "technical",
        "match_score":      0.80,
    },
    {
        "question_bank_id": "uuid-003",
        "question_text":    "팀 갈등을 해결한 경험을 말해주세요.",
        "question_type":    "personality",
        "match_score":      0.70,
    },
]


# ══════════════════════════════════════════════════════════════
# MySQL 폴백 경로 (Pinecone 미설정)
# ══════════════════════════════════════════════════════════════

class TestSearchSimilarQuestionsMysqlFallback:

    def _mock_settings_no_pinecone(self):
        """Pinecone 설정이 없는 settings mock"""
        mock_settings = MagicMock()
        mock_settings.PINECONE_API_KEY    = ""
        mock_settings.PINECONE_INDEX_NAME = ""
        return mock_settings

    def test_pinecone_미설정시_mysql_폴백(self):
        """PINECONE_API_KEY 없으면 MySQL 폴백 사용"""
        with patch("apps.analysis.services.question_rag_service.settings", self._mock_settings_no_pinecone()), \
             patch("apps.analysis.services.question_rag_service._mysql_fallback", return_value=MOCK_DB_CANDIDATES) as mock_fallback:
            result = search_similar_questions(JD_KEYWORDS_BACKEND, top_k=10)

        mock_fallback.assert_called_once()
        assert result == MOCK_DB_CANDIDATES

    def test_결과_반환_형식(self):
        """반환 결과가 list[dict] 형식"""
        with patch("apps.analysis.services.question_rag_service.settings", self._mock_settings_no_pinecone()), \
             patch("apps.analysis.services.question_rag_service._mysql_fallback", return_value=MOCK_DB_CANDIDATES):
            result = search_similar_questions(JD_KEYWORDS_BACKEND)

        print(f"\n결과: {len(result)}개")
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)

    def test_source_question_bank_설정(self):
        """MySQL 폴백 결과에 source='question_bank' 포함"""
        candidates_with_source = [dict(c, source="question_bank") for c in MOCK_DB_CANDIDATES]
        with patch("apps.analysis.services.question_rag_service.settings", self._mock_settings_no_pinecone()), \
             patch("apps.analysis.services.question_rag_service._mysql_fallback", return_value=candidates_with_source):
            result = search_similar_questions(JD_KEYWORDS_BACKEND)

        for item in result:
            assert item.get("source") == "question_bank", \
                f"source가 'question_bank'가 아님: {item.get('source')}"

    def test_pinecone_실패시_mysql_폴백(self):
        """Pinecone 검색 실패 → MySQL 폴백으로 전환"""
        mock_settings = MagicMock()
        mock_settings.PINECONE_API_KEY    = "fake-key"
        mock_settings.PINECONE_INDEX_NAME = "fake-index"

        with patch("apps.analysis.services.question_rag_service.settings", mock_settings), \
             patch("apps.analysis.services.question_rag_service._pinecone_search", side_effect=Exception("Connection failed")), \
             patch("apps.analysis.services.question_rag_service._mysql_fallback", return_value=MOCK_DB_CANDIDATES) as mock_fallback:
            result = search_similar_questions(JD_KEYWORDS_BACKEND)

        mock_fallback.assert_called_once()
        print(f"\nPinecone 실패 → MySQL 폴백: {len(result)}개")

    def test_빈_키워드_mysql_폴백(self):
        """빈 키워드도 에러 없이 처리"""
        with patch("apps.analysis.services.question_rag_service.settings", self._mock_settings_no_pinecone()), \
             patch("apps.analysis.services.question_rag_service._mysql_fallback", return_value=[]):
            result = search_similar_questions(JD_KEYWORDS_EMPTY)

        assert result == []

    def test_top_k_전달(self):
        """top_k 파라미터가 내부 함수에 전달되는지"""
        with patch("apps.analysis.services.question_rag_service.settings", self._mock_settings_no_pinecone()), \
             patch("apps.analysis.services.question_rag_service._mysql_fallback", return_value=[]) as mock_fallback:
            search_similar_questions(JD_KEYWORDS_BACKEND, top_k=5)

        call_args = mock_fallback.call_args
        assert call_args[0][1] == 5 or call_args[1].get("top_k") == 5 or 5 in call_args[0], \
            f"top_k=5가 _mysql_fallback에 전달되지 않음: {call_args}"


# ══════════════════════════════════════════════════════════════
# Pinecone 경로 (설정 있을 때)
# ══════════════════════════════════════════════════════════════

class TestSearchSimilarQuestionsPinecone:

    PINECONE_RESULTS = [
        {
            "question_bank_id": "pc-uuid-001",
            "question_text":    "Redis TTL 전략에 대해 설명해주세요.",
            "question_type":    "technical",
            "source":           "question_bank",
            "matched_keyword":  "",
            "similarity_score": 0.92,
            "type":             "technical",
            "text":             "Redis TTL 전략에 대해 설명해주세요.",
        },
    ]

    def test_pinecone_설정_있으면_pinecone_호출(self):
        """Pinecone 설정이 있으면 _pinecone_search 호출"""
        mock_settings = MagicMock()
        mock_settings.PINECONE_API_KEY    = "valid-key"
        mock_settings.PINECONE_INDEX_NAME = "valid-index"

        with patch("apps.analysis.services.question_rag_service.settings", mock_settings), \
             patch("apps.analysis.services.question_rag_service._pinecone_search", return_value=self.PINECONE_RESULTS) as mock_pc:
            result = search_similar_questions(JD_KEYWORDS_BACKEND)

        mock_pc.assert_called_once()
        assert result == self.PINECONE_RESULTS
        print(f"\nPinecone 결과: {len(result)}개")
