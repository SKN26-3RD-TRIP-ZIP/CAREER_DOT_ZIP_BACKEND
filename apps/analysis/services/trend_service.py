"""
대기업 최근 동향 조회 서비스.

Tavily Search API로 회사의 최근 뉴스를 검색해 질문 생성 프롬프트에
주입할 짧은 요약 문자열을 만든다.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TIMEOUT_SECONDS = 5


def get_company_recent_trends(company_name: str) -> str:
    """회사명으로 최근 동향(뉴스) 요약을 조회한다.

    TAVILY_API_KEY 미설정, 검색 결과 없음, 예외 발생 시 빈 문자열을 반환한다
    (예외 전파 금지 — 대기업 컨텍스트를 보강하는 best-effort 정보이며,
    실패해도 질문 생성 흐름 전체가 막혀서는 안 된다).
    """
    api_key = getattr(settings, "TAVILY_API_KEY", "")
    company_name = (company_name or "").strip()
    if not api_key or not company_name:
        return ""

    try:
        response = requests.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": api_key,
                "query": f"{company_name} 최근 채용 동향 사업 소식",
                "topic": "news",
                "search_depth": "basic",
                "max_results": 5,
                "days": 90,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("get_company_recent_trends 검색 실패 (company=%s): %s", company_name, e)
        return ""

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        return ""

    lines = []
    for item in results[:3]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        snippet = (item.get("content") or "").strip()[:120]
        lines.append(f"- {title}: {snippet}" if snippet else f"- {title}")

    return "\n".join(lines)
