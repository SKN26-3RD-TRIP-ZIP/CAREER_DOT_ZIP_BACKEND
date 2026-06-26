"""
question_merge_service 단위 테스트 (임베딩 모킹)

테스트 대상:
  merge_and_deduplicate()   RAG + LLM 질문 통합 & 중복 제거

임베딩 모킹:
  get_embeddings를 patch해 실제 API 호출 없이 테스트.
  유사도는 cosine_similarity 실제 구현을 사용.

실행:
  pytest apps/analysis/tests/test_question_merge_service.py -v -s
"""

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")
from unittest.mock import patch
from apps.analysis.services.question_merge_service import merge_and_deduplicate


# ══════════════════════════════════════════════════════════════
# 헬퍼 — 방향이 다른 단위 벡터 생성
# ══════════════════════════════════════════════════════════════

def make_orthogonal_vectors(n: int, dim: int = 16) -> list[list[float]]:
    """서로 직교하는(유사도 0) n개의 벡터 생성"""
    vecs = []
    for i in range(min(n, dim)):
        v = [0.0] * dim
        v[i] = 1.0
        vecs.append(v)
    # dim보다 많이 필요하면 방향을 약간씩 다르게
    for i in range(len(vecs), n):
        v = [0.0] * dim
        v[i % dim] = 1.0
        v[(i + 1) % dim] = 0.01
        vecs.append(v)
    return vecs


def make_identical_vectors(n: int, dim: int = 16) -> list[list[float]]:
    """모두 동일한 벡터 (유사도 1)"""
    v = [1.0] + [0.0] * (dim - 1)
    return [v[:] for _ in range(n)]


LLM_QUESTIONS = [
    {"type": "technical",   "text": "Redis 캐싱 전략을 설명해주세요.",      "source": "jd",          "basis": "Redis"},
    {"type": "personality", "text": "팀 갈등을 해결한 경험이 있나요?",     "source": "coverletter",  "basis": "협업"},
    {"type": "experience",  "text": "가장 어려웠던 기술 문제를 말해주세요.", "source": "project",      "basis": "문제해결"},
    {"type": "technical",   "text": "Django ORM의 N+1 문제 해결 방법은?",  "source": "jd",          "basis": "Django"},
]

RAG_QUESTIONS = [
    {"type": "technical",   "question_text": "Redis에 대해 설명해주세요.",  "question_type": "technical",   "source": "question_bank", "matched_keyword": "Redis",  "similarity_score": 0.85},
    {"type": "personality", "question_text": "갈등 해결 방식을 말해주세요.", "question_type": "personality", "source": "question_bank", "matched_keyword": "협업",   "similarity_score": 0.78},
    {"type": "experience",  "question_text": "어려운 프로젝트 경험은?",     "question_type": "experience",  "source": "question_bank", "matched_keyword": "프로젝트","similarity_score": 0.82},
]


def _add_text_field(qs: list[dict]) -> list[dict]:
    """RAG 질문에 text 필드 추가 (merge 내부에서 사용)"""
    result = []
    for q in qs:
        q = dict(q)
        q.setdefault("text", q.get("question_text", ""))
        result.append(q)
    return result


# ══════════════════════════════════════════════════════════════
# 빈 입력
# ══════════════════════════════════════════════════════════════

class TestMergeEmptyInputs:

    def test_둘_다_비어있으면_빈_리스트(self):
        with patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=[]):
            result = merge_and_deduplicate([], [])
        assert result == []

    def test_llm만_있고_rag_비어있음(self):
        llm = LLM_QUESTIONS[:3]
        all_vecs = make_orthogonal_vectors(len(llm))
        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=all_vecs):
            result = merge_and_deduplicate([], llm)
        print(f"\nLLM만 입력: {len(result)}개")
        assert isinstance(result, list)

    def test_rag만_있고_llm_비어있음(self):
        rag = _add_text_field(RAG_QUESTIONS)
        all_vecs = make_orthogonal_vectors(len(rag))
        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=all_vecs):
            result = merge_and_deduplicate(rag, [])
        print(f"\nRAG만 입력: {len(result)}개")
        assert isinstance(result, list)


# ══════════════════════════════════════════════════════════════
# 중복 제거
# ══════════════════════════════════════════════════════════════

class TestMergeDeduplicate:

    def test_동일_질문_중복제거(self):
        """LLM 질문과 RAG 질문이 동일(유사도 1.0)하면 RAG 제거"""
        llm = [{"type": "technical", "text": "Redis 캐싱이란?", "source": "jd", "basis": "Redis"}]
        rag = _add_text_field([{"type": "technical", "question_text": "Redis 캐싱이란?", "question_type": "technical", "source": "question_bank", "matched_keyword": "Redis", "similarity_score": 0.9}])

        # 두 질문에 동일한 벡터 부여 → 유사도 1.0
        identical_vecs = make_identical_vectors(2)
        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=identical_vecs):
            result = merge_and_deduplicate(rag, llm, target_counts={"technical": 2, "personality": 0, "experience": 0})

        # LLM 우선이므로 1개만 남아야 함
        print(f"\n중복 제거 결과: {len(result)}개")
        assert len(result) == 1
        assert result[0]["source"] == "jd"  # LLM 질문이 남아야 함

    def test_직교_질문_둘_다_유지(self):
        """완전히 다른 질문은 둘 다 유지"""
        llm = [{"type": "technical", "text": "Redis 캐싱이란?",   "source": "jd", "basis": "Redis"}]
        rag = _add_text_field([{"type": "technical", "question_text": "Docker 컨테이너란?", "question_type": "technical", "source": "question_bank", "matched_keyword": "Docker", "similarity_score": 0.7}])

        orthogonal_vecs = make_orthogonal_vectors(2)
        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=orthogonal_vecs):
            result = merge_and_deduplicate(rag, llm, target_counts={"technical": 4, "personality": 0, "experience": 0})

        print(f"\n직교 질문 결과: {len(result)}개")
        assert len(result) == 2

    def test_llm_우선순위(self):
        """같은 내용이면 LLM 질문이 RAG보다 우선"""
        llm = [{"type": "technical", "text": "LLM 질문", "source": "jd", "basis": ""}]
        rag = _add_text_field([{"type": "technical", "question_text": "LLM 질문", "question_type": "technical", "source": "question_bank", "matched_keyword": "", "similarity_score": 0.9}])

        identical_vecs = make_identical_vectors(2)
        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=identical_vecs):
            result = merge_and_deduplicate(rag, llm, target_counts={"technical": 1, "personality": 0, "experience": 0})

        assert len(result) == 1
        assert result[0]["source"] == "jd", "LLM 질문이 우선되어야 함"


# ══════════════════════════════════════════════════════════════
# target_counts 준수
# ══════════════════════════════════════════════════════════════

class TestMergeTargetCounts:

    def test_기본_target_counts(self):
        """기본값: personality=3, technical=4, experience=3"""
        # 충분한 질문 준비
        llm = (
            [{"type": "personality", "text": f"인성질문{i}", "source": "coverletter", "basis": ""} for i in range(4)]
            + [{"type": "technical",   "text": f"기술질문{i}", "source": "jd",          "basis": ""} for i in range(5)]
            + [{"type": "experience",  "text": f"경험질문{i}", "source": "project",      "basis": ""} for i in range(4)]
        )
        n = len(llm)
        orthogonal_vecs = make_orthogonal_vectors(n)

        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=orthogonal_vecs):
            result = merge_and_deduplicate([], llm)

        types = [q["type"] for q in result]
        print(f"\n타입별: personality={types.count('personality')} technical={types.count('technical')} experience={types.count('experience')}")
        assert types.count("personality") <= 3
        assert types.count("technical")   <= 4
        assert types.count("experience")  <= 3

    def test_커스텀_target_counts(self):
        """커스텀 target_counts 적용"""
        llm = [{"type": "technical", "text": f"기술질문{i}", "source": "jd", "basis": ""} for i in range(6)]
        orthogonal_vecs = make_orthogonal_vectors(len(llm))

        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=orthogonal_vecs):
            result = merge_and_deduplicate([], llm, target_counts={"technical": 3, "personality": 0, "experience": 0})

        assert len(result) <= 3
        assert all(q["type"] == "technical" for q in result)


# ══════════════════════════════════════════════════════════════
# 내부 필드 정리
# ══════════════════════════════════════════════════════════════

class TestMergeFieldCleanup:

    def test_임시_필드_제거(self):
        """_emb, _priority 등 내부 필드가 결과에 남지 않아야 함"""
        llm = [{"type": "technical", "text": "Redis 질문", "source": "jd", "basis": ""}]
        vecs = make_orthogonal_vectors(1)

        with patch("apps.analysis.services.question_merge_service.get_client"), \
             patch("apps.analysis.services.question_merge_service.get_embeddings", return_value=vecs):
            result = merge_and_deduplicate([], llm, target_counts={"technical": 1, "personality": 0, "experience": 0})

        for q in result:
            assert "_emb"      not in q, "_emb 내부 필드가 결과에 남아있음"
            assert "_priority" not in q, "_priority 내부 필드가 결과에 남아있음"
