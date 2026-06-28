"""약점 태그 기반 추천 질문 서비스 (E7.9).

약점 태그명 → question_bank 쿼리 전략을 매핑하여
QuestionBankItem에서 연습 질문을 추천한다.
"""

import logging

from django.core.cache import cache

from apps.question_bank.models import QuestionBankItem

logger = logging.getLogger("feedback_ai.recommendation_service")

# 세션 추천 결과 캐시(#5). 완료된 세션의 약점 태그는 안정적이라 매 조회마다
# 재집계(답변 prefetch + 전체 question_bank 스캔/스코어링)할 필요가 없다.
# total_limit 별로 다른 키를 쓰고, 버전 키로 일괄 무효화한다.
_RECO_CACHE_TTL = 60 * 30  # 30분


def _reco_version(session_id) -> int:
    return cache.get(f"weakness_recos_ver:{session_id}", 0)


def invalidate_weakness_reco_cache(session_id) -> None:
    """리포트 재생성 등 약점 태그가 바뀔 수 있을 때 캐시를 무효화한다."""
    try:
        cache.incr(f"weakness_recos_ver:{session_id}")
    except ValueError:  # 키 없음 → 첫 무효화
        cache.set(f"weakness_recos_ver:{session_id}", 1)

# 약점 태그명 → (question_type 후보, 키워드, difficulty 선호)
_TAG_STRATEGY: dict[str, dict] = {
    "weak_technical_understanding": {
        "question_types": ["technical"],
        "keywords": ["기술", "개념", "원리", "아키텍처", "구조"],
        "difficulty": "easy",
    },
    "weak_technical_reasoning": {
        "question_types": ["technical"],
        "keywords": ["트레이드오프", "비교", "선택", "의사결정", "설계"],
        "difficulty": "medium",
    },
    "weak_specificity": {
        "question_types": ["technical", "job"],  # "experience" 타입 없음 → job으로 대체
        "keywords": ["구체적", "성과", "결과", "수치", "경험"],
        "difficulty": "medium",
    },
    "weak_evidence": {
        "question_types": ["technical", "job"],  # "experience" 타입 없음 → job으로 대체
        "keywords": ["수치", "지표", "성과", "개선", "측정"],
        "difficulty": "medium",
    },
    "weak_question_relevance": {
        "question_types": ["personality", "job"],
        "keywords": ["핵심", "답변", "구성", "논리", "질문"],
        "difficulty": "easy",
    },
    "weak_personal_contribution": {
        "question_types": ["job", "personality"],  # "experience" 타입 없음 → job으로 대체
        "keywords": ["역할", "기여", "주도", "오너십", "책임"],
        "difficulty": "medium",
    },
    "weak_jd_fit": {
        "question_types": ["job", "technical"],
        "keywords": ["직무", "역량", "스킬", "요건", "경험"],
        "difficulty": "medium",
    },
    "weak_problem_solving_process": {
        "question_types": ["personality", "job"],  # "experience" 타입 없음 → job으로 대체
        "keywords": ["문제해결", "과정", "분석", "접근", "방법"],
        "difficulty": "medium",
    },
    "weak_result_impact": {
        "question_types": ["technical", "job"],  # "experience" 타입 없음 → job으로 대체
        "keywords": ["결과", "성과", "효과", "개선", "달성"],
        "difficulty": "medium",
    },
    "weak_answer_structure": {
        "question_types": ["personality", "job"],
        "keywords": ["구조", "논리", "흐름", "정리", "핵심"],
        "difficulty": "easy",
    },
    "excessive_filler_words": {
        "question_types": ["personality"],
        "keywords": ["말하기", "발표", "소통", "전달", "표현"],
        "difficulty": "easy",
    },
    "frequent_long_pauses": {
        "question_types": ["personality"],
        "keywords": ["순발력", "유연성", "즉흥", "대처", "커뮤니케이션"],
        "difficulty": "easy",
    },
    "unbalanced_speech_pace": {
        "question_types": ["personality"],
        "keywords": ["발화", "답변 속도", "호흡", "전달력"],
        "difficulty": "easy",
    },
}

_DEFAULT_STRATEGY = {
    "question_types": ["personality", "technical"],
    "keywords": [],
    "difficulty": "medium",
}


def _score_item(item: QuestionBankItem, keywords: list[str]) -> int:
    """키워드 매칭 점수 계산."""
    item_kws = {str(k).strip().lower() for k in (item.keywords or [])}
    return sum(1 for kw in keywords if kw.lower() in item_kws or kw.lower() in item.question_text)


def get_recommended_questions_for_tags(
    weakness_tag_names: list[str],
    limit_per_tag: int = 3,
    total_limit: int = 10,
) -> list[dict]:
    """약점 태그 목록에서 연습 질문을 추천한다.

    Args:
        weakness_tag_names: 추천 기준이 될 약점 태그명 목록 (우선순위 순).
        limit_per_tag: 태그당 최대 추천 질문 수.
        total_limit: 전체 최대 반환 수.

    Returns:
        추천 질문 dict 목록 (question_text, question_type, difficulty, weakness_tag, match_score).
    """
    results: list[dict] = []
    seen_ids: set = set()

    # 활성 질문을 1회만 로드해 태그별 풀스캔(최대 N회)을 제거하고 메모리에서 재사용한다.
    all_active_items = list(QuestionBankItem.objects.filter(is_active=True))

    for tag_name in weakness_tag_names:
        strategy = _TAG_STRATEGY.get(tag_name, _DEFAULT_STRATEGY)
        q_types = strategy["question_types"]
        keywords = strategy["keywords"]
        difficulty = strategy.get("difficulty")

        typed_items = [it for it in all_active_items if it.question_type in q_types]
        pool = [it for it in typed_items if (not difficulty or it.difficulty == difficulty)]

        scored = [
            (_score_item(item, keywords), item)
            for item in pool
            if item.id not in seen_ids
        ]

        # difficulty 필터로 결과가 없으면 difficulty 제한 없이 재시도
        if not scored and difficulty:
            scored = [
                (_score_item(item, keywords), item)
                for item in typed_items
                if item.id not in seen_ids
            ]

        scored.sort(key=lambda x: (-x[0], str(x[1].id)))

        added = 0
        for score, item in scored:
            if added >= limit_per_tag:
                break
            if len(results) >= total_limit:
                break
            seen_ids.add(item.id)
            results.append({
                "question_bank_id": str(item.id),
                "question_text": item.question_text,
                "answer_example": item.answer_example or "",
                "question_type": item.question_type,
                "difficulty": item.difficulty,
                "keywords": item.keywords,
                "weakness_tag": tag_name,
                "match_score": score,
            })
            added += 1

        if len(results) >= total_limit:
            break

    logger.info(
        "get_recommended_questions_for_tags: tags=%s, returned=%d",
        weakness_tag_names,
        len(results),
    )
    return results


def get_session_weakness_recommended_questions(session, total_limit: int = 10) -> dict:
    """세션의 모든 답변 약점 태그를 집계하여 추천 질문을 반환한다.

    Returns:
        {
            "weakness_tags": [...],      # 세션 전체 약점 태그 빈도 Top5
            "recommended_questions": [...],
        }
    """
    from collections import Counter

    cache_key = f"weakness_recos:{session.id}:{total_limit}:v{_reco_version(session.id)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 약점 태그 빈도 집계
    tag_counter: Counter = Counter()
    for answer in session.answers.prefetch_related("weakness_mappings__weakness_tag").all():
        for wm in answer.weakness_mappings.all():
            tag_counter[wm.weakness_tag.tag_name] += 1

    top_tags = [name for name, _ in tag_counter.most_common(5)]

    recommended = get_recommended_questions_for_tags(
        weakness_tag_names=top_tags,
        limit_per_tag=3,
        total_limit=total_limit,
    )

    result = {
        "weakness_tags": [
            {"tag_name": name, "count": cnt}
            for name, cnt in tag_counter.most_common(5)
        ],
        "recommended_questions": recommended,
    }
    cache.set(cache_key, result, _RECO_CACHE_TTL)
    return result
