# apps/evaluation/test_sufficiency_bridge.py
"""resolve_answer_sufficiency 회귀 테스트.

interview 팀 공개 인터페이스(InterviewAIChainService.evaluate_answer_sufficiency)
경로로의 전환을 고정한다. 폴백(_build_sufficiency_payload) 제거 이후,
evaluation 쪽 계약이 유지되는지 검증한다.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.evaluation.services.sufficiency_bridge import resolve_answer_sufficiency

BRIDGE = "apps.evaluation.services.sufficiency_bridge.InterviewAIChainService"


@override_settings(OPENAI_USE_MOCK=False)
class ResolveAnswerSufficiencyTest(SimpleTestCase):
    def test_calls_public_method_and_unpacks_contract(self):
        """공개 메서드를 answer 인스턴스로 1회 호출하고 두 키를 그대로 풀어 반환한다."""
        answer = object()
        tags = [{"tag_name": "vague_experience"}]
        selected = {"tag_name": "vague_experience"}

        with patch(BRIDGE) as service_cls:
            service = service_cls.return_value
            service.evaluate_answer_sufficiency.return_value = {
                "answer_weakness_tags": tags,
                "selected_weakness_tag": selected,
            }

            result = resolve_answer_sufficiency(answer)

        self.assertEqual(result, (tags, selected))
        service.evaluate_answer_sufficiency.assert_called_once_with(answer)
        # 레거시 private 경로는 더 이상 사용하지 않는다.
        service.judge_answer_sufficiency.assert_not_called()

    def test_graceful_degrade_on_exception(self):
        """공개 메서드가 예외를 던지면 평가가 죽지 않고 ([], None) 으로 격리된다."""
        with patch(BRIDGE) as service_cls:
            service = service_cls.return_value
            service.evaluate_answer_sufficiency.side_effect = RuntimeError("boom")

            result = resolve_answer_sufficiency(object())

        self.assertEqual(result, ([], None))

    def test_missing_keys_fall_back_to_safe_defaults(self):
        """반환 dict에 키가 없어도 ([], None) 기본값으로 안전하게 처리한다."""
        with patch(BRIDGE) as service_cls:
            service = service_cls.return_value
            service.evaluate_answer_sufficiency.return_value = {}

            result = resolve_answer_sufficiency(object())

        self.assertEqual(result, ([], None))

    def test_request_sufficiency_short_circuits_without_calling_service(self):
        """request 흐름(turns API)에서 sufficiency 가 오면 LLM 호출 없이 그대로 쓴다."""
        tags = [{"tag_name": "shallow_reasoning"}]
        selected = {"tag_name": "shallow_reasoning"}

        with patch(BRIDGE) as service_cls:
            result = resolve_answer_sufficiency(
                object(),
                request_sufficiency={
                    "answer_weakness_tags": tags,
                    "selected_weakness_tag": selected,
                },
            )

        self.assertEqual(result, (tags, selected))
        service_cls.assert_not_called()

    @override_settings(OPENAI_USE_MOCK=True)
    def test_mock_env_skips_sufficiency_call(self):
        """OPENAI_USE_MOCK=True 로컬 환경에서는 sufficiency 호출을 스킵한다."""
        with patch(BRIDGE) as service_cls:
            result = resolve_answer_sufficiency(object())

        self.assertEqual(result, ([], None))
        service_cls.assert_not_called()
