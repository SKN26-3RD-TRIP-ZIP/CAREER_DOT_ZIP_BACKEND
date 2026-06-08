from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class TestInterviewOpenAIChainCommandTest(SimpleTestCase):
    @override_settings(OPENAI_API_KEY="", INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=False)
    def test_command_runs_sufficiency_chain_with_mock_fallback(self):
        out = StringIO()

        call_command(
            "test_interview_openai_chain",
            "--chain",
            "sufficiency",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn('"chain": "sufficiency"', output)
        self.assertIn('"real_call_enabled": false', output)
        self.assertIn('"sufficiency"', output)
        self.assertIn('"next_action"', output)

    @override_settings(OPENAI_API_KEY="", INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=False)
    def test_command_runs_all_chains_with_mock_fallback(self):
        out = StringIO()

        call_command(
            "test_interview_openai_chain",
            "--chain",
            "all",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn('"questions"', output)
        self.assertIn('"sufficiency"', output)
        self.assertIn('"followup"', output)

    @override_settings(OPENAI_API_KEY="", INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=False)
    def test_command_skips_real_call_without_api_key(self):
        out = StringIO()

        call_command(
            "test_interview_openai_chain",
            "--chain",
            "all",
            "--use-real",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("OPENAI_API_KEY", output)
        self.assertIn("실제 호출을 건너뜁니다", output)
