import os
import math
from django.conf import settings
from openai import OpenAI
from langsmith import wrappers

# LangSmith 트레이싱 설정
os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"]    = settings.LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"]    = settings.LANGCHAIN_PROJECT


def get_client() -> OpenAI:
    """LangSmith 트레이싱이 적용된 OpenAI 클라이언트를 반환."""
    return wrappers.wrap_openai(OpenAI())


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
