from django.test import SimpleTestCase, override_settings

from apps.interview.services.ai_chain_engine_factory import get_ai_chain_engine
from apps.interview.services.ai_chain_mock_engine import AIChainMockEngine
from apps.interview.services.ai_chain_openai_engine import AIChainOpenAIEngine
from apps.interview.services.ai_chain_service import InterviewAIChainService


class AIChainEngineFactoryTest(SimpleTestCase):
    @override_settings(
        INTERVIEW_AI_CHAIN_ENGINE='mock',
        INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=False,
    )
    def test_get_ai_chain_engine_returns_mock_engine_by_default(self):
        engine = get_ai_chain_engine()

        self.assertIsInstance(engine, AIChainMockEngine)

    def test_get_ai_chain_engine_returns_mock_engine_when_engine_name_is_mock(self):
        engine = get_ai_chain_engine("mock")

        self.assertIsInstance(engine, AIChainMockEngine)

    def test_get_ai_chain_engine_returns_openai_engine_when_engine_name_is_openai(self):
        engine = get_ai_chain_engine("openai")

        self.assertIsInstance(engine, AIChainOpenAIEngine)

    @override_settings(INTERVIEW_AI_CHAIN_ENGINE="mock")
    def test_get_ai_chain_engine_uses_mock_settings_value(self):
        engine = get_ai_chain_engine()

        self.assertIsInstance(engine, AIChainMockEngine)

    @override_settings(INTERVIEW_AI_CHAIN_ENGINE="openai")
    def test_get_ai_chain_engine_uses_openai_settings_value(self):
        engine = get_ai_chain_engine()

        self.assertIsInstance(engine, AIChainOpenAIEngine)

    def test_get_ai_chain_engine_raises_error_when_engine_is_not_supported(self):
        with self.assertRaises(ValueError):
            get_ai_chain_engine("unsupported")

    @override_settings(
        INTERVIEW_AI_CHAIN_ENGINE='mock',
        INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=False,
    )
    def test_interview_ai_chain_service_uses_factory_engine_by_default(self):
        service = InterviewAIChainService()

        self.assertIsInstance(service.engine, AIChainMockEngine)

    def test_interview_ai_chain_service_can_receive_engine_name(self):
        service = InterviewAIChainService(engine_name="openai")

        self.assertIsInstance(service.engine, AIChainOpenAIEngine)

    def test_interview_ai_chain_service_can_receive_custom_engine(self):
        class DummyEngine:
            def get_personas(self):
                return [{"persona_type": "dummy"}]

        dummy_engine = DummyEngine()
        service = InterviewAIChainService(engine=dummy_engine)

        self.assertIs(service.engine, dummy_engine)
        self.assertEqual(service.get_personas(), [{"persona_type": "dummy"}])
