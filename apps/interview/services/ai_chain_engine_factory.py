"""
AI 면접 Chain engine factory.

배치 위치:
apps/interview/services/ai_chain_engine_factory.py

역할:
- AI Chain engine 선택 로직을 한 곳에서 관리
- 기본값은 mock engine으로 유지
- OpenAI/Claude 등 engine 추가 시 service 호출부 변경을 최소화
"""

from django.conf import settings

from apps.interview.services.ai_chain_mock_engine import AIChainMockEngine
from apps.interview.services.ai_chain_openai_engine import AIChainOpenAIEngine


ENGINE_MOCK = "mock"
ENGINE_OPENAI = "openai"


def get_ai_chain_engine(engine_name: str | None = None):
    """설정값에 맞는 AI Chain engine 인스턴스를 반환한다.

    현재 지원 engine:
    - mock: DB/LLM 없이 동작하는 deterministic mock engine
    - openai: OpenAI engine 기본 구조. 현재는 mock fallback으로 기존 동작 유지
    """
    selected_engine = (
        engine_name
        or getattr(settings, "INTERVIEW_AI_CHAIN_ENGINE", ENGINE_MOCK)
        or ENGINE_MOCK
    ).lower()

    if selected_engine == ENGINE_MOCK:
        return AIChainMockEngine()

    if selected_engine == ENGINE_OPENAI:
        return AIChainOpenAIEngine()

    raise ValueError(f"Unsupported AI Chain engine: {selected_engine}")
