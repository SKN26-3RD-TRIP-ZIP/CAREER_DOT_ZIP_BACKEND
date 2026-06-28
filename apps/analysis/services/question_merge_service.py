"""
Pipeline 3 - ④ 질문 통합 & 중복 제거

역할:
  ②번 질문 은행 RAG 결과와 ③번 LLM 생성 결과를 합치고,
  의미 중복 질문을 임베딩 유사도 기준으로 제거한 뒤
  유형별 개수를 조정해 최종 질문 목록을 반환한다.

포함 함수:
  merge_and_deduplicate()   질문 통합 + 의미 중복 제거 + 유형별 개수 조정
"""

from .utils import get_client, get_embeddings, cosine_similarity

_DEFAULT_TARGET = {"personality": 2, "technical": 2, "experience": 1}


def merge_and_deduplicate(
    rag_questions: list[dict],
    llm_questions: list[dict],
    target_counts: dict | None = None,
    similarity_threshold: float = 0.88,
    github_questions: list[dict] | None = None,
) -> list[dict]:
    """
    RAG 검색 질문과 LLM 생성 질문을 합쳐 중복을 제거하고 유형별 개수를 맞춘다.

    중복 제거 전략:
      1. 전체 질문 텍스트를 한 번에 임베딩
      2. 유형별 그룹 내에서 threshold 이상 유사 쌍 발견 시 RAG 질문 제거 (LLM 우선)
      3. 남은 질문에서 target_counts만큼 선택 (LLM → RAG 순)
      4. 부족하면 RAG 보충, 남으면 임베딩 순 상위 N개 선택

    github_questions:
      GitHub repo 검증 기반 질문 (source=project|combined).
      target_counts 슬롯을 뺏지 않고 결과에 '추가'된다 — 단, 최종 결과와
      의미 중복인 것만 제거하고 덧붙인다. (검증 질문은 차별화 가치라 보존)
    """
    if target_counts is None:
        target_counts = _DEFAULT_TARGET
    github_questions = github_questions or []

    for q in llm_questions:
        q["_priority"] = 1
    for q in rag_questions:
        q["_priority"] = 2

    all_questions = llm_questions + rag_questions
    if not all_questions and not github_questions:
        return []

    client = get_client()
    texts  = [q.get("text") or q.get("question_text", "") for q in all_questions]
    embeddings = get_embeddings(texts, client)

    for q, emb in zip(all_questions, embeddings):
        q["_emb"] = emb

    result: list[dict] = []
    for q_type, count in target_counts.items():
        group = [
            q for q in all_questions
            if q.get("type") == q_type or q.get("question_type") == q_type
        ]
        group.sort(key=lambda x: x["_priority"])

        kept: list[dict] = []
        for candidate in group:
            is_dup = any(
                cosine_similarity(candidate["_emb"], kept_q["_emb"]) >= similarity_threshold
                for kept_q in kept
            )
            if not is_dup:
                kept.append(candidate)
            if len(kept) >= count:
                break

        for q in kept:
            q.pop("_emb", None)
            q.pop("_priority", None)

        result.extend(kept)

    # 임시 필드 정리 (result에 포함되지 않은 항목도 정리)
    for q in all_questions:
        q.pop("_emb", None)
        q.pop("_priority", None)

    # GitHub 검증 질문은 슬롯과 무관하게 '추가'한다.
    # 단, 이미 선정된 result와 의미 중복인 것만 제거하고 덧붙인다.
    if github_questions:
        base_texts = [q.get("text") or q.get("question_text", "") for q in result]
        gh_texts   = [q.get("text", "") for q in github_questions]
        embs       = get_embeddings(base_texts + gh_texts, client)
        base_embs  = embs[:len(base_texts)]
        gh_embs    = embs[len(base_texts):]

        for gq, ge in zip(github_questions, gh_embs):
            is_dup = any(
                cosine_similarity(ge, be) >= similarity_threshold for be in base_embs
            )
            if not is_dup:
                gq.pop("_emb", None)
                gq.pop("_priority", None)
                result.append(gq)
                base_embs.append(ge)        # 이후 GitHub 질문끼리도 중복 제거

    return result
