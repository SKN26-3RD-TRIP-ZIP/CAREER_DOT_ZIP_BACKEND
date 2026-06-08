import os
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
    return text.strip().replace("```json", "").replace("```", "").strip()
