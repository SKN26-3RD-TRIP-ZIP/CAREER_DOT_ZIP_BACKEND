from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone

from apps.interview.models import InterviewSession
from apps.report.models import FinalReport
from ..models import ApiErrorLog, LlmUsageLog

User = get_user_model()

# 모델별 단가 (USD / 1M tokens, input/output). 2026-06 기준, 변동 가능.
# 출처: apps/evaluation/benchmarks/llm_eval_benchmark.py 의 PRICING.
# 표에 없는 모델은 비용 계산에서 제외(과소 추정될 수 있음).
LLM_PRICING = {
    "gpt-4o-mini":  (0.15, 0.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4o":       (2.50, 10.00),
    "gpt-5.5":      (5.00, 30.00),
}


def _price_for(model):
    """모델명에 맞는 단가를 찾는다.

    OpenAI 응답의 model은 'gpt-4o-mini-2024-07-18'처럼 날짜 스냅샷이 붙어
    단가표 키와 정확히 일치하지 않는다. 가장 긴 접두사 키로 매칭해
    'gpt-4o-mini-...'가 'gpt-4o'가 아니라 'gpt-4o-mini'에 매칭되도록 한다.
    """
    if model in LLM_PRICING:
        return LLM_PRICING[model]
    best = None
    for key in LLM_PRICING:
        if model.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return LLM_PRICING[best] if best else None


def _monthly_llm_cost_usd(month_start):
    """이번 달 LlmUsageLog를 모델별로 묶어 토큰×단가로 비용(USD)을 추정한다."""
    usage = (
        LlmUsageLog.objects
        .filter(created_at__date__gte=month_start)
        .values('model')
        .annotate(prompt=Sum('prompt_tokens'), completion=Sum('completion_tokens'))
    )
    cost = 0.0
    for row in usage:
        price = _price_for(row['model'])
        if not price:
            continue
        in_price, out_price = price
        cost += (row['prompt'] or 0) / 1_000_000 * in_price
        cost += (row['completion'] or 0) / 1_000_000 * out_price
    return round(cost, 4)


def _growth_rate(current, previous):
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def build_member_stats():
    """회원 증감 통계 (이번 달 대비 지난 달 증가율 포함)."""
    today = timezone.now().date()
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    this_month_new = User.objects.filter(created_at__date__gte=this_month_start).count()
    last_month_new = User.objects.filter(
        created_at__date__gte=last_month_start,
        created_at__date__lte=last_month_end,
    ).count()

    this_month_active_new = User.objects.filter(
        created_at__date__gte=this_month_start, status='active'
    ).count()
    last_month_active_new = User.objects.filter(
        created_at__date__gte=last_month_start,
        created_at__date__lte=last_month_end,
        status='active',
    ).count()

    return {
        'total': User.objects.count(),
        'active': User.objects.filter(status='active').count(),
        'dormant': User.objects.filter(status='dormant').count(),
        'banned': User.objects.filter(status='banned').count(),
        'withdrawn': User.objects.filter(status='withdrawn').count(),
        'today': User.objects.filter(created_at__date=today).count(),
        'total_growth_rate': _growth_rate(this_month_new, last_month_new),
        'active_growth_rate': _growth_rate(this_month_active_new, last_month_active_new),
    }


def build_dashboard_stats():
    """관리자 대시보드 요약 통계."""
    today = timezone.now().date()
    week_ago = today - timedelta(days=6)
    weekly_qs = (
        InterviewSession.objects
        .filter(created_at__date__gte=week_ago)
        .values('created_at__date')
        .annotate(count=Count('id'))
        .order_by('created_at__date')
    )
    weekly_map = {str(row['created_at__date']): row['count'] for row in weekly_qs}
    weekly_sessions = [
        {'date': str(week_ago + timedelta(days=i)), 'count': weekly_map.get(str(week_ago + timedelta(days=i)), 0)}
        for i in range(7)
    ]

    # 최근 24시간 시스템 에러 수 (API 5xx/미처리 예외, ApiErrorLog 기반 실제 수치)
    since_24h = timezone.now() - timedelta(hours=24)
    error_count = ApiErrorLog.objects.filter(created_at__gte=since_24h).count()

    # LLM 호출량 (LlmUsageLog 기반 실제 수치)
    ai_calls = LlmUsageLog.objects.count()

    # 이번 달 LLM 비용 추정 (USD)
    month_start = today.replace(day=1)
    monthly_cost = _monthly_llm_cost_usd(month_start)

    return {
        'total_members': User.objects.count(),
        'active_members': User.objects.filter(status='active').count(),
        'suspended_members': User.objects.filter(status='dormant').count(),
        'banned_members': User.objects.filter(status='banned').count(),
        'total_sessions': InterviewSession.objects.count(),
        'active_users': InterviewSession.objects.values('user_id').distinct().count(),
        'total_reports': FinalReport.objects.count(),
        'error_count': error_count,
        'ai_calls': ai_calls,
        # 이번 달 LLM 비용 추정치 (USD). 표에 있는 모델만 합산.
        'monthly_cost': monthly_cost,
        'cost_currency': 'USD',
        'weekly_sessions': weekly_sessions,
    }
