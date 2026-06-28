import os
import math
from django.conf import settings
from openai import OpenAI
from langsmith import wrappers

# LangSmith 트레이싱 설정
os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"]    = settings.LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"]    = settings.LANGCHAIN_PROJECT
os.environ["LANGSMITH_ENDPOINT"]   = settings.LANGSMITH_ENDPOINT


def get_client() -> OpenAI:
    """LangSmith 트레이싱이 적용된 OpenAI 클라이언트를 반환."""
    return wrappers.wrap_openai(OpenAI())


def log_llm_usage(response, user=None):
    """chat.completions.create() 응답에서 토큰 사용량을 DB에 저장."""
    from apps.admin_api.models import LlmUsageLog
    try:
        LlmUsageLog.objects.create(
            user=user,
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
    except Exception:
        pass


def clean_json(text: str) -> str:
    """LLM 응답에서 마크다운 코드블록을 제거하고 순수 JSON 문자열만 반환."""
    return text.strip().replace("```json", "").replace("```", "").strip()


def get_embeddings(texts: list[str], client) -> list[list[float]]:
    """
    텍스트 목록을 한 번의 API 호출로 임베딩 벡터 리스트로 변환.
    text-embedding-3-small 모델 사용.
    빈 리스트가 들어오면 빈 리스트 반환.
    """
    if not texts:
        return []
    res = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in res.data]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    두 벡터 간 코사인 유사도를 계산한다. (0.0 ~ 1.0)
    영벡터가 입력될 경우 0.0 반환.
    """
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x ** 2 for x in a))
    norm_b = math.sqrt(sum(x ** 2 for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


import re as _re_json
import json as _json_safe
import logging as _logging_safe

_pja_logger = _logging_safe.getLogger(__name__)


def parse_json_array(text: str) -> list:
    """LLM 응답 문자열에서 JSON 배열을 안전하게 파싱한다.

    실제 LLM은 가끔 마크다운 코드펜스나 앞뒤 설명을 덧붙이거나, 드물게 잘못된
    JSON을 반환한다. 이때 전체 요청을 JSONDecodeError 로 중단시키지 않고 안전하게
    빈 리스트로 degrade 한다(상위에서 빈 답변 필드로 처리).

    처리 순서:
      1) 코드펜스 제거(clean_json) 후 json.loads
      2) 실패 시 첫 '[' ~ 마지막 ']' 구간만 추출해 재시도
      3) 그래도 실패하면 경고 로그 후 [] 반환 (예외 전파/성공 위장/허위 생성 없음)

    반환은 항상 list. list 가 아닌 JSON(객체 등)도 [] 로 처리한다.
    """
    cleaned = clean_json(text or "")
    if not cleaned:
        return []
    try:
        data = _json_safe.loads(cleaned)
        return data if isinstance(data, list) else []
    except (_json_safe.JSONDecodeError, TypeError):
        pass

    match = _re_json.search(r"\[.*\]", cleaned, _re_json.S)
    if match:
        try:
            data = _json_safe.loads(match.group(0))
            return data if isinstance(data, list) else []
        except _json_safe.JSONDecodeError:
            pass

    _pja_logger.warning("parse_json_array: LLM 응답을 JSON 배열로 파싱하지 못해 빈 결과로 degrade 합니다.")
    return []
