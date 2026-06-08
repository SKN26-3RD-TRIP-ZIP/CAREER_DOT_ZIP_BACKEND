"""
AI 면접 Chain LLM 응답 파싱 유틸.

배치 위치:
apps/interview/services/ai_chain_response_parser.py

역할:
- LLM 응답에서 JSON object/list를 안정적으로 추출
- markdown code fence, 설명 문장 + JSON 혼합 응답 처리
- 파싱 실패 시 fallback 기본값 반환 또는 명시적 예외 발생
"""

from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import Any


_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json|JSON)?\s*(.*?)```",
    re.DOTALL,
)


def strip_json_code_fence(raw_text: str) -> str:
    """Markdown code fence 안의 JSON 문자열만 추출한다.

    code fence가 없으면 원문을 strip해서 반환한다.
    """
    text = (raw_text or "").strip()
    match = _CODE_FENCE_PATTERN.search(text)
    if not match:
        return text
    return match.group(1).strip()


def extract_json_text(raw_text: str) -> str | None:
    """문자열에서 첫 번째 JSON object/list 후보를 추출한다."""
    text = strip_json_code_fence(raw_text)
    if not text:
        return None

    try:
        json.loads(text)
        return text
    except JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    start_indexes = [
        index
        for index, char in enumerate(text)
        if char in ("{", "[")
    ]

    for start_index in start_indexes:
        candidate = text[start_index:]
        try:
            _, end_index = decoder.raw_decode(candidate)
        except JSONDecodeError:
            continue
        return candidate[:end_index].strip()

    return None


def parse_llm_json(raw_response: Any, default: Any = None) -> Any:
    """LLM 응답을 JSON으로 파싱한다.

    dict/list가 이미 들어온 경우 그대로 반환한다.
    파싱 실패 시 default를 반환한다.
    """
    if isinstance(raw_response, (dict, list)):
        return raw_response

    if raw_response is None:
        return default

    json_text = extract_json_text(str(raw_response))
    if not json_text:
        return default

    try:
        return json.loads(json_text)
    except JSONDecodeError:
        return default


def require_llm_json(raw_response: Any) -> Any:
    """LLM 응답을 JSON으로 파싱하고, 실패하면 ValueError를 발생시킨다."""
    parsed = parse_llm_json(raw_response, default=None)
    if parsed is None:
        raise ValueError("Failed to parse LLM response as JSON.")
    return parsed


def parse_llm_json_object(raw_response: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """LLM 응답을 JSON object(dict)로 파싱한다."""
    fallback = default if default is not None else {}
    parsed = parse_llm_json(raw_response, default=fallback)
    return parsed if isinstance(parsed, dict) else fallback


def parse_llm_json_list(raw_response: Any, default: list[Any] | None = None) -> list[Any]:
    """LLM 응답을 JSON list로 파싱한다."""
    fallback = default if default is not None else []
    parsed = parse_llm_json(raw_response, default=fallback)
    return parsed if isinstance(parsed, list) else fallback
