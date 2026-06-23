from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone

from apps.interview.models import InterviewSession
from apps.report.models import FinalReport
from ..models import AuditLog, LlmUsageLog

User = get_user_model()


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

    # 최근 24시간 감사 로그 기반 에러 비율 (시스템 에러 프록시)
    since_24h = timezone.now() - timedelta(hours=24)
    audit_24h_total = AuditLog.objects.filter(created_at__gte=since_24h).count()
    error_24h = AuditLog.objects.filter(created_at__gte=since_24h, action_type__icontains='error').count()
    error_rate = round((error_24h / audit_24h_total * 100), 1) if audit_24h_total > 0 else 0.0

    # LLM 호출량 (LlmUsageLog 기반 실제 수치)
    ai_calls = LlmUsageLog.objects.count()

    return {
        'total_members': User.objects.count(),
        'active_members': User.objects.filter(status='active').count(),
        'suspended_members': User.objects.filter(status='dormant').count(),
        'banned_members': User.objects.filter(status='banned').count(),
        'total_sessions': InterviewSession.objects.count(),
        'active_users': InterviewSession.objects.values('user_id').distinct().count(),
        'total_reports': FinalReport.objects.count(),
        'error_count': error_24h,
        'ai_calls': ai_calls,
        # 단가 정보가 없어 비용 산정은 보류 (토큰 합계만 노출)
        'monthly_cost': 0,
        'weekly_sessions': weekly_sessions,
        'system_health': {
            'stt_status': 'normal',
            'error_rate_24h': error_rate,
            'audit_count_24h': audit_24h_total,
        },
    }
