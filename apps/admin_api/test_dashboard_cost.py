"""대시보드 monthly_cost(이번 달 LLM 비용 추정, USD) 계산 테스트."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.admin_api.models import LlmUsageLog
from apps.admin_api.services.dashboard_service import build_dashboard_stats


class MonthlyCostTests(TestCase):
    def test_sums_tokens_by_model_price(self):
        # gpt-4o-mini 단가 (0.15, 0.60) USD / 1M tokens
        LlmUsageLog.objects.create(
            model='gpt-4o-mini', prompt_tokens=1_000_000, completion_tokens=1_000_000,
        )
        stats = build_dashboard_stats()
        # 0.15(input) + 0.60(output) = 0.75
        self.assertEqual(stats['monthly_cost'], 0.75)
        self.assertEqual(stats['cost_currency'], 'USD')

    def test_unknown_model_is_excluded(self):
        LlmUsageLog.objects.create(
            model='made-up-model', prompt_tokens=1_000_000, completion_tokens=1_000_000,
        )
        self.assertEqual(build_dashboard_stats()['monthly_cost'], 0)

    def test_previous_month_is_excluded(self):
        log = LlmUsageLog.objects.create(
            model='gpt-4o-mini', prompt_tokens=1_000_000, completion_tokens=0,
        )
        # created_at은 auto_now_add라 생성 후 지난달로 백데이트
        last_month = timezone.now().replace(day=1) - timedelta(days=1)
        LlmUsageLog.objects.filter(pk=log.pk).update(created_at=last_month)

        self.assertEqual(build_dashboard_stats()['monthly_cost'], 0)

    def test_dated_snapshot_model_name_is_matched(self):
        # OpenAI 응답은 'gpt-4o-mini-2024-07-18'처럼 스냅샷명을 돌려준다.
        # 가장 긴 접두사 매칭으로 gpt-4o가 아니라 gpt-4o-mini(0.15/0.60)에 잡혀야 한다.
        LlmUsageLog.objects.create(
            model='gpt-4o-mini-2024-07-18', prompt_tokens=1_000_000, completion_tokens=1_000_000,
        )
        self.assertEqual(build_dashboard_stats()['monthly_cost'], 0.75)
