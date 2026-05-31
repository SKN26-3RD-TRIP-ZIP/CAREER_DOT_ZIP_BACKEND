from __future__ import annotations

import json
import re
from typing import Any


class LLMJsonParseError(ValueError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    """LLM 응답에서 JSON object를 추출한다.

    대응 케이스:
    - 순수 JSON 문자열
    - ```json fenced code block
    - 앞뒤 설명이 섞인 JSON object
    """

    cleaned = text.strip()

    # 1. pure JSON
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. fenced code block
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if code_block:
        try:
            parsed = json.loads(code_block.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise LLMJsonParseError(f"JSON code block 파싱 실패: {exc}") from exc

    # 3. first JSON-like object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and start < end:
        candidate = cleaned[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise LLMJsonParseError(f"본문 내 JSON object 파싱 실패: {exc}") from exc

    raise LLMJsonParseError("LLM 응답에서 JSON object를 찾지 못했습니다.")
