from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSettings:
    """LLM 실행 설정.

    - mock 모드에서는 사용하지 않는다.
    - llm 모드에서는 OPENAI_API_KEY가 필요하다.
    """

    openai_api_key: str | None
    openai_model: str = "gpt-4o-mini"


def get_llm_settings() -> LLMSettings:
    return LLMSettings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )
