"""
Pipeline 3 - ② 질문 은행 RAG (Pinecone 검색)

역할:
  Pipeline 1 ①에서 추출한 JD 키워드를 쿼리로 Pinecone에서 유사 질문을 검색한다.
  Pinecone 미연동 환경에서는 MySQL 키워드 매칭으로 자동 폴백한다.

포함 함수:
  search_similar_questions()   Pinecone 유사 질문 검색 (MySQL 폴백 포함)
"""

import logging

from django.conf import settings

from .utils import get_client, get_embeddings

logger = logging.getLogger(__name__)


def search_similar_questions(
    jd_keywords: dict,
    top_k: int = 20,
) -> list[dict]:
    """
    JD 키워드를 임베딩해 Pinecone에서 유사 질문 Top K를 검색한다.
    PINECONE_API_KEY 또는 PINECONE_INDEX_NAME이 비어 있으면 MySQL 폴백으로 전환한다.

    반환 형식:
    [
        {
            "question_bank_id": "uuid",
            "question_text":    "Redis의 캐싱 전략에 대해 설명해주세요.",
            "question_type":    "technical",
            "source":           "question_bank",
            "matched_keyword":  "Redis",
            "similarity_score": 0.87,
        },
        ...
    ]
    """
    api_key    = getattr(settings, "PINECONE_API_KEY", "")
    index_name = getattr(settings, "PINECONE_INDEX_NAME", "")

    if not api_key or not index_name:
        logger.warning("Pinecone 설정 없음 — MySQL 폴백 사용")
        return _mysql_fallback(jd_keywords, top_k)

    try:
        return _pinecone_search(jd_keywords, top_k, api_key, index_name)
    except Exception as e:
        logger.warning("Pinecone 검색 실패 (%s) — MySQL 폴백 사용", e)
        return _mysql_fallback(jd_keywords, top_k)


def _pinecone_search(
    jd_keywords: dict,
    top_k: int,
    api_key: str,
    index_name: str,
) -> list[dict]:
    """Pinecone에서 유사 질문을 벡터 검색한다."""
    from pinecone import Pinecone

    tech_keywords  = jd_keywords.get("tech_keywords", [])
    trait_keywords = jd_keywords.get("trait_keywords", [])
    query_text     = " ".join(tech_keywords + trait_keywords)

    if not query_text.strip():
        return []

    client     = get_client()
    query_vec  = get_embeddings([query_text], client)[0]

    pc     = Pinecone(api_key=api_key)
    index  = pc.Index(index_name)
    result = index.query(vector=query_vec, top_k=top_k, include_metadata=True)

    questions = []
    for match in result.matches:
        meta = match.metadata or {}
        questions.append({
            "question_bank_id": meta.get("question_id", match.id),
            "question_text":    meta.get("question_text", ""),
            "question_type":    meta.get("type", "technical"),
            "source":           "question_bank",
            "matched_keyword":  "",
            "similarity_score": round(match.score, 4),
            # merge_and_deduplicate에서 사용하는 내부 키
            "type":             meta.get("type", "technical"),
            "text":             meta.get("question_text", ""),
        })

    return questions


def _mysql_fallback(jd_keywords: dict, top_k: int) -> list[dict]:
    """Pinecone 미사용 환경에서 MySQL 키워드 매칭으로 대체한다."""
    from apps.question_bank.services.question_bank_service import get_question_candidates

    tech_keywords  = jd_keywords.get("tech_keywords", [])
    trait_keywords = jd_keywords.get("trait_keywords", [])

    candidates = get_question_candidates(
        jd_keywords=tech_keywords + trait_keywords,
        limit=top_k,
    )

    for c in candidates:
        c["source"] = "question_bank"
        c.setdefault("matched_keyword", "")
        c["similarity_score"] = c.pop("match_score", 0)
        # merge_and_deduplicate에서 사용하는 내부 키
        c.setdefault("type", c.get("question_type", "technical"))
        c.setdefault("text", c.get("question_text", ""))

    return candidates
