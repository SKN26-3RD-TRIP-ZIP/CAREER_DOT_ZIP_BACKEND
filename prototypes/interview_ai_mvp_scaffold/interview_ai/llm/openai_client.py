from __future__ import annotations

from interview_ai_mvp_scaffold.config import get_llm_settings


class OpenAIClientNotConfigured(RuntimeError):
    pass


def call_openai_chat(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> str:
    """OpenAI Chat Completions 호출.

    openai 패키지는 실제 LLM 모드에서만 import한다.
    mock 테스트에서는 API 키나 openai 패키지가 없어도 이 파일이 실행되지 않는다.
    """

    settings = get_llm_settings()

    if not settings.openai_api_key:
        raise OpenAIClientNotConfigured(
            "OPENAI_API_KEY가 설정되어 있지 않습니다. .env 또는 환경변수에 API 키를 설정해주세요."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise OpenAIClientNotConfigured(
            "openai 패키지가 설치되어 있지 않습니다. pip install openai 를 실행해주세요."
        ) from exc

    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI 응답 content가 비어 있습니다.")

    return content
