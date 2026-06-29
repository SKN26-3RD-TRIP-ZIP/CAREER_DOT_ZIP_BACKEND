from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import PointHistory
from apps.interview.models import InterviewSession
from apps.prompt.models import AdminPromptTestRun
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
        .filter(created_at__gte=month_start)
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


def _parse_period(start=None, end=None):
    return parse_datetime(start) if start else None, parse_datetime(end) if end else None


def _apply_created_period(queryset, start_dt, end_dt):
    if start_dt:
        queryset = queryset.filter(created_at__gte=start_dt)
    if end_dt:
        queryset = queryset.filter(created_at__lt=end_dt)
    return queryset


def _apply_report_period(queryset, start_dt, end_dt):
    if start_dt:
        queryset = queryset.filter(generated_at__gte=start_dt)
    if end_dt:
        queryset = queryset.filter(generated_at__lt=end_dt)
    return queryset


def build_dashboard_stats(start=None, end=None):
    start_dt, end_dt = _parse_period(start, end)
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
    error_queryset = _apply_created_period(ApiErrorLog.objects.all(), start_dt, end_dt)
    error_count = error_queryset.count() if (start_dt or end_dt) else error_queryset.filter(created_at__gte=since_24h).count()

    # LLM 호출량 (LlmUsageLog 기반 실제 수치)
    llm_queryset = _apply_created_period(LlmUsageLog.objects.all(), start_dt, end_dt)
    ai_calls = llm_queryset.count()

    # 이번 달 LLM 비용 추정 (USD)
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_cost = _monthly_llm_cost_usd(month_start)
    point_queryset = _apply_created_period(PointHistory.objects.all(), start_dt, end_dt)
    report_queryset = _apply_report_period(FinalReport.objects.all(), start_dt, end_dt)
    session_queryset = _apply_created_period(InterviewSession.objects.all(), start_dt, end_dt)
    member_queryset = _apply_created_period(User.objects.all(), start_dt, end_dt)
    point_summary = point_queryset.aggregate(
        earned=Sum('amount', filter=Q(transaction_type=PointHistory.TRANSACTION_EARN)),
        used=Sum('amount', filter=Q(transaction_type=PointHistory.TRANSACTION_USE)),
        refunded=Sum('amount', filter=Q(transaction_type=PointHistory.TRANSACTION_REFUND)),
    )
    report_by_status = {
        row['status']: row['count']
        for row in report_queryset.values('status').annotate(count=Count('id'))
    }
    prompt_version_usage = {
        str(row['prompt_version_id']): row['count']
        for row in AdminPromptTestRun.objects.values('prompt_version_id').annotate(count=Count('id'))
        if row['prompt_version_id'] is not None
    }
    usage_source = {
        'mock': report_queryset.filter(
            Q(summary__evaluation_metadata__is_mock=True)
            | Q(summary__source__in=['MOCK', 'CAREER_ZIP_MOCK'])
        ).count(),
        'fallback': report_queryset.filter(summary__evaluation_metadata__evaluation_status='FALLBACK').count(),
        'real_llm': report_queryset.exclude(
            Q(summary__evaluation_metadata__is_mock=True)
            | Q(summary__source__in=['MOCK', 'CAREER_ZIP_MOCK'])
            | Q(summary__evaluation_metadata__evaluation_status='FALLBACK')
        ).count(),
    }

    return {
        'period': {
            'start': start_dt.isoformat() if start_dt else None,
            'end': end_dt.isoformat() if end_dt else None,
        },
        'total_members': User.objects.count(),
        'active_members': User.objects.filter(status='active').count(),
        'suspended_members': User.objects.filter(status='dormant').count(),
        'banned_members': User.objects.filter(status='banned').count(),
        'withdrawn_members': User.objects.filter(status='withdrawn').count(),
        'new_members': member_queryset.count() if (start_dt or end_dt) else User.objects.filter(created_at__date=today).count(),
        'verified_members': User.objects.filter(is_verified=True).count(),
        'total_sessions': session_queryset.count(),
        'completed_sessions': session_queryset.filter(status='completed').count(),
        'active_users': session_queryset.values('user_id').distinct().count(),
        'total_reports': report_queryset.count(),
        'reports': {
            'by_status': report_by_status,
            'success': report_queryset.filter(status=FinalReport.STATUS_DONE).count(),
            'failed': report_queryset.filter(status=FinalReport.STATUS_FAILED).count(),
        },
        'evaluations': {
            'completed': report_queryset.filter(summary__evaluation_metadata__evaluation_status='COMPLETED').count(),
            'failed': report_queryset.filter(status=FinalReport.STATUS_FAILED).count(),
        },
        'usage_source': usage_source,
        'prompt_versions': prompt_version_usage,
        'error_count': error_count,
        'ai_calls': ai_calls,
        # 이번 달 LLM 비용 추정치 (USD). 표에 있는 모델만 합산.
        'monthly_cost': monthly_cost,
        'cost_currency': 'USD',
        'points': {
            'earned': point_summary['earned'] or 0,
            'used': point_summary['used'] or 0,
            'refunded': point_summary['refunded'] or 0,
            'transaction_count': point_queryset.count(),
        },
        'weekly_sessions': weekly_sessions,
    }
