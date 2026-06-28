"""SBERT 기반 하드스킬 깊이 검증 서비스 (E7.5).

SBERT 유사도(70%) + LLM 정량 평가(30%)를 결합하여
기술 질문 답변의 깊이를 100점 만점으로 산출한다.

모델: paraphrase-multilingual-MiniLM-L12-v2 (한국어 지원, 경량)
"""

import logging
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger("feedback_ai.sbert_service")

# settings.py에 SBERT_MODEL_NAME 설정 시 오버라이드 가능
SBERT_MODEL_NAME = getattr(
    settings,
    "SBERT_MODEL_NAME",
    "paraphrase-multilingual-MiniLM-L12-v2",
)


@lru_cache(maxsize=1)
def _get_sbert_model():
    """SentenceTransformer 모델을 싱글턴으로 로드 (최초 1회만 로드)."""
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("SBERT 모델 로드 시작: %s", SBERT_MODEL_NAME)
        model = SentenceTransformer(SBERT_MODEL_NAME)
        logger.info("SBERT 모델 로드 완료")
        return model
    except Exception as e:
        logger.error("SBERT 모델 로드 실패: %s", str(e), exc_info=True)
        return None


def _cosine_similarity(vec_a, vec_b) -> float:
    """두 벡터의 코사인 유사도를 반환한다 (0.0 ~ 1.0)."""
    import numpy as np
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def compute_sbert_similarities(
    answer_text: str,
    reference_db_text: str | None = None,
    reference_readme_text: str | None = None,
) -> dict:
    """SBERT 임베딩 기반 유사도 계산.

    Args:
        answer_text: 지원자 답변 텍스트.
        reference_db_text: DB 기술스택 설명 / JD 기술 요건 텍스트.
        reference_readme_text: 질문 텍스트 또는 기술 문서 텍스트.

    Returns:
        {
            "sbert_db_similarity": float,        # 0.0~1.0 (reference_db 기준)
            "sbert_readme_similarity": float,    # 0.0~1.0 (reference_readme 기준)
            "sbert_combined_score": float,       # 0~100 (가중 평균 × 100)
            "model_available": bool,
        }
    """
    model = _get_sbert_model()
    if model is None:
        logger.warning("SBERT 모델 미사용 — 유사도 0 반환")
        return {
            "sbert_db_similarity": None,
            "sbert_readme_similarity": None,
            "sbert_combined_score": 0.0,
            "model_available": False,
        }

    try:
        texts_to_encode = [answer_text]
        if reference_db_text:
            texts_to_encode.append(reference_db_text)
        if reference_readme_text:
            texts_to_encode.append(reference_readme_text)

        embeddings = model.encode(texts_to_encode, convert_to_numpy=True)
        answer_emb = embeddings[0]

        idx = 1
        db_sim = None
        readme_sim = None

        if reference_db_text:
            db_sim = _cosine_similarity(answer_emb, embeddings[idx])
            idx += 1
        if reference_readme_text:
            readme_sim = _cosine_similarity(answer_emb, embeddings[idx])

        # 가중 평균: db 60%, readme 40% (둘 다 있을 때)
        if db_sim is not None and readme_sim is not None:
            combined = db_sim * 0.6 + readme_sim * 0.4
        elif db_sim is not None:
            combined = db_sim
        elif readme_sim is not None:
            combined = readme_sim
        else:
            combined = 0.0

        return {
            "sbert_db_similarity": round(db_sim, 4) if db_sim is not None else None,
            "sbert_readme_similarity": round(readme_sim, 4) if readme_sim is not None else None,
            "sbert_combined_score": round(combined * 100, 2),
            "model_available": True,
        }

    except Exception as e:
        logger.error("SBERT 유사도 계산 실패: %s", str(e), exc_info=True)
        return {
            "sbert_db_similarity": None,
            "sbert_readme_similarity": None,
            "sbert_combined_score": 0.0,
            "model_available": False,
        }


def compute_tech_depth_score(
    sbert_combined_score: float,
    llm_concept_score: float,
    sbert_weight: float = 0.70,
    llm_weight: float = 0.30,
) -> float:
    """SBERT(70%) + LLM 정량 평가(30%) 혼합 최종 기술 깊이 점수 산출.

    Args:
        sbert_combined_score: SBERT 유사도 기반 점수 (0~100).
        llm_concept_score: LLM이 판단한 개념 이해 점수 (0~100).
        sbert_weight: SBERT 가중치 (기본 0.70 = 70%).
        llm_weight: LLM 가중치 (기본 0.30 = 30%).

    Returns:
        혼합 점수 (0~100, float).
    """
    raw = sbert_combined_score * sbert_weight + llm_concept_score * llm_weight
    return min(round(raw, 2), 100.0)


def get_reference_texts_for_answer(answer) -> tuple[str | None, str | None]:
    """답변의 세션 컨텍스트에서 SBERT 비교 레퍼런스 텍스트를 추출한다.

    - reference_db_text     : JD 기술 요건 + 포지션 텍스트
    - reference_readme_text : expected_technical_keywords 태그의 source_text_excerpt.
                              태그가 없으면 None (non-technical 질문 또는 인터뷰팀 미저장).
    """
    reference_db_text = None
    reference_readme_text = None

    try:
        session = answer.session
        jd = getattr(session, "jd", None)
        if jd:
            parts = [
                jd.position or "",
                jd.job_requirements or "",
                jd.original_text or "",
            ]
            reference_db_text = " ".join(p for p in parts if p).strip() or None

        question = getattr(answer, "question", None)
        if question:
            keyword_tag = next(
                (t for t in question.source_tags.all()
                 if t.source_label == "expected_technical_keywords"),
                None,
            )
            if keyword_tag:
                if not keyword_tag.source_text_excerpt:
                    logger.warning(
                        "expected_technical_keywords 태그 존재하나 source_text_excerpt 비어있음 (question_id=%s)",
                        question.id,
                    )
                reference_readme_text = keyword_tag.source_text_excerpt or None

    except Exception as e:
        logger.warning("레퍼런스 텍스트 추출 실패: %s", str(e))

    return reference_db_text, reference_readme_text
