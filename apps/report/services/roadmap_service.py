"""roadmap_service: weakness_tags 기반 개인화 학습 로드맵 생성.

RoadmapCache + RoadmapItem 둘 다 존재하면 LLM 재호출 없이 DB 반환.
"""
import json
import logging
from collections import Counter

from django.conf import settings
from django.db import transaction
from openai import OpenAI

from apps.report.models import RoadmapItem, RoadmapCache

_VALID_PRIORITIES = {"high", "mid", "low"}

logger = logging.getLogger("feedback_ai.roadmap_service")

openai_client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))

_SYSTEM_PROMPT = """당신은 개발자 취업 면접 코치입니다.
지원자의 면접 약점 태그 목록을 분석하여 개인화 학습 로드맵을 JSON 형식으로 생성합니다.

응답은 반드시 아래 JSON 스키마를 따르세요:
{
  "week_priority_text": "이번 주 집중할 약점을 요약한 1~2문장",
  "practice_question": "오늘 연습할 면접 질문 1개 (실제 면접에서 나올 법한 구체적인 질문)",
  "items": [
    {
      "item_id": "item-001",
      "title": "학습 항목 제목 (간결하게)",
      "description": "구체적인 학습 방법과 목표를 설명하는 2~3문장",
      "priority": "high"
    }
  ]
}

규칙:
- items는 3~5개
- priority는 "high", "mid", "low" 중 하나
- item_id는 "item-001", "item-002" 형식으로 순번 부여
- 응답은 JSON만 출력 (마크다운 코드블록 없이)
"""

_USER_PROMPT_TEMPLATE = """다음은 이 지원자의 면접 약점 태그 목록입니다:

{tags_text}

위 약점을 기반으로 개인화 학습 로드맵을 생성해주세요."""


def _get_weakness_tags_from_session(session) -> list[str]:
    """세션 전체 답변의 weakness_tag를 빈도 순으로 반환 (최대 5개)."""
    tag_counter: Counter = Counter()
    for answer in session.answers.prefetch_related("weakness_mappings__weakness_tag").all():
        for wm in answer.weakness_mappings.all():
            tag_counter[wm.weakness_tag.tag_name] += 1

    try:
        report_summary = session.final_report.summary or {}
        triggered = report_summary.get("dynamically_triggered_tags", {})
        for tag in triggered.get("weakness_tags", []):
            tag_name = tag.get("tag_name") if isinstance(tag, dict) else tag
            if tag_name:
                tag_counter[tag_name] += 1
    except Exception:
        pass

    return [name for name, _ in tag_counter.most_common(5)]


def _call_llm(weakness_tags: list[str]) -> dict:
    """gpt-4o-mini 1회 호출, JSON 파싱 후 반환."""
    if not weakness_tags:
        tags_text = "특정 약점 태그 없음 (전반적인 면접 역량 향상 목표)"
    else:
        tags_text = "\n".join(f"- {tag}" for tag in weakness_tags)

    user_prompt = _USER_PROMPT_TEMPLATE.format(tags_text=tags_text)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            timeout=20.0,
        )
        raw = response.choices[0].message.content
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("LLM roadmap JSON 파싱 실패: %s", e)
        raise
    except Exception as e:
        logger.error("LLM roadmap 호출 실패: %s", e, exc_info=True)
        raise


def get_or_create_roadmap(session) -> dict:
    """캐시가 있으면 DB 반환, 없으면 LLM 호출 후 DB 저장 후 반환.

    캐시 판정: RoadmapCache AND RoadmapItem 둘 다 존재해야 캐시 히트.
    한쪽만 있는 불완전 상태이면 LLM 재호출해 모두 갱신한다.
    """
    # 캐시 히트 확인 (읽기 전용, 트랜잭션 밖)
    existing_items = list(session.roadmap_items.order_by("created_at").all())
    try:
        cache = session.roadmap_cache
        if existing_items:
            return {
                "week_priority_text": cache.week_priority_text,
                "practice_question": cache.practice_question,
                "items": existing_items,
            }
    except RoadmapCache.DoesNotExist:
        cache = None

    # LLM 호출 (트랜잭션 밖 - 잠금 범위 최소화)
    weakness_tags = _get_weakness_tags_from_session(session)
    llm_result = _call_llm(weakness_tags)

    week_priority_text = llm_result.get("week_priority_text", "")
    practice_question = llm_result.get("practice_question", "")
    raw_items = llm_result.get("items", [])

    # DB 저장: select_for_update로 동시 요청 중복 생성 방지
    with transaction.atomic():
        from apps.interview.models import InterviewSession as _IS
        _IS.objects.select_for_update().get(pk=session.pk)

        # 락 획득 후 재확인 (double-check)
        fresh_items = list(session.roadmap_items.order_by("created_at").all())
        try:
            fresh_cache = session.roadmap_cache
            if fresh_items:
                return {
                    "week_priority_text": fresh_cache.week_priority_text,
                    "practice_question": fresh_cache.practice_question,
                    "items": fresh_items,
                }
        except RoadmapCache.DoesNotExist:
            fresh_cache = None

        # 캐시 갱신 또는 신규 생성
        if fresh_cache is not None:
            fresh_cache.week_priority_text = week_priority_text
            fresh_cache.practice_question = practice_question
            fresh_cache.save(update_fields=["week_priority_text", "practice_question"])
            cache = fresh_cache
        else:
            cache = RoadmapCache.objects.create(
                session=session,
                week_priority_text=week_priority_text,
                practice_question=practice_question,
            )

        # 불완전 캐시 잔재 정리
        if fresh_items:
            RoadmapItem.objects.filter(session=session).delete()

        created_items = []
        for idx, raw in enumerate(raw_items, start=1):
            raw_priority = raw.get("priority", "mid")
            safe_priority = raw_priority if raw_priority in _VALID_PRIORITIES else "mid"
            item_id = raw.get("item_id") or f"item-{idx:03d}"
            item = RoadmapItem.objects.create(
                session=session,
                item_id=item_id,
                title=raw.get("title", ""),
                description=raw.get("description", ""),
                priority=safe_priority,
            )
            created_items.append(item)

    return {
        "week_priority_text": cache.week_priority_text,
        "practice_question": cache.practice_question,
        "items": created_items,
    }
