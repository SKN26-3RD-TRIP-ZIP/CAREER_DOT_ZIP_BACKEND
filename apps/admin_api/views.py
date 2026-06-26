from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.analysis.models import AnalysisSession, JdAnalysis
from apps.accounts.models import PointHistory
from apps.accounts.services.points import admin_adjust_points
from apps.document.models import UploadedDocument
from apps.input.models import JobDescription, ResumeMaster, CoverLetter, ProjectExperience, UserProfile
from apps.interview.models import GuardrailEvent, InterviewSession
from apps.report.models import FinalReport
from .models import AuditLog
from .permissions import IsAdminUserOrRole
from .serializers import (
    AuditLogQuerySerializer,
    AuditLogSerializer,
    AdminPointAdjustSerializer,
    AdminGuardrailEventQuerySerializer,
    AdminGuardrailEventSerializer,
    AdminPointHistoryQuerySerializer,
    AdminPointHistorySerializer,
    MemberInviteSerializer,
    MemberListQuerySerializer,
    MemberListSerializer,
    MemberStatusSerializer,
)


User = get_user_model()


def paginate(queryset, page, size):
    start = (page - 1) * size
    return queryset[start:start + size]


class AdminAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserOrRole]


class MemberListView(AdminAPIView):
    def get(self, request):
        query_serializer = MemberListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        now = timezone.now()
        members = User.objects.annotate(
            practice_count=Count(
                'interview_sessions',
                filter=Q(interview_sessions__status='completed'),
                distinct=True,
            ),
            monthly_session_count=Count(
                'interview_sessions',
                filter=Q(
                    interview_sessions__created_at__year=now.year,
                    interview_sessions__created_at__month=now.month,
                ),
                distinct=True,
            ),
            report_count=Count('interview_sessions__final_report', distinct=True),
        ).order_by('-created_at')
        if params.get('status'):
            members = members.filter(status=params['status'])
        if params.get('search'):
            q = params['search']
            members = members.filter(Q(name__icontains=q) | Q(email__icontains=q))

        total = members.count()
        results = paginate(members, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': MemberListSerializer(results, many=True).data,
            }
        )


class MemberStatusView(AdminAPIView):
    def patch(self, request, member_id):
        serializer = MemberStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        if request.user.id == member_id and new_status in ('dormant', 'banned', 'suspended'):
            return Response(
                {'detail': 'You cannot change status of your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            member = get_object_or_404(User.objects.select_for_update(), id=member_id)
            before_status = member.status
            member.status = new_status
            member.save(update_fields=('status', 'updated_at'))
            AuditLog.objects.create(
                actor=request.user,
                action_type='member_status_change',
                target_type=User._meta.db_table,
                target_id=str(member.id),
                before_value={'status': before_status},
                after_value={'status': member.status},
            )

        return Response(
            {
                'id': member.id,
                'status': member.status,
                'updated_at': member.updated_at,
            }
        )


class MemberStatsView(AdminAPIView):
    def get(self, request):
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

        def growth_rate(current, previous):
            if previous == 0:
                return None
            return round((current - previous) / previous * 100, 1)

        return Response({
            'total': User.objects.count(),
            'active': User.objects.filter(status='active').count(),
            'dormant': User.objects.filter(status='dormant').count(),
            'banned': User.objects.filter(status='banned').count(),
            'today': User.objects.filter(created_at__date=today).count(),
            'total_growth_rate': growth_rate(this_month_new, last_month_new),
            'active_growth_rate': growth_rate(this_month_active_new, last_month_active_new),
        })


class DashboardStatsView(AdminAPIView):
    def get(self, request):
        total_members = User.objects.count()
        active_members = User.objects.filter(status='active').count()
        suspended_members = User.objects.filter(status='dormant').count()
        banned_members = User.objects.filter(status='banned').count()

        total_sessions = InterviewSession.objects.count()
        active_users = InterviewSession.objects.values('user_id').distinct().count()
        total_reports = FinalReport.objects.count()

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

        # 24h error count from audit logs as proxy for system errors
        since_24h = timezone.now() - timedelta(hours=24)
        audit_24h_total = AuditLog.objects.filter(created_at__gte=since_24h).count()
        error_24h = AuditLog.objects.filter(created_at__gte=since_24h, action_type__icontains='error').count()
        error_rate = round((error_24h / audit_24h_total * 100), 1) if audit_24h_total > 0 else 0.0
        point_summary = PointHistory.objects.aggregate(
            earned=Sum('amount', filter=Q(transaction_type=PointHistory.TRANSACTION_EARN)),
            used=Sum('amount', filter=Q(transaction_type=PointHistory.TRANSACTION_USE)),
            refunded=Sum('amount', filter=Q(transaction_type=PointHistory.TRANSACTION_REFUND)),
        )
        guardrail_by_category = {
            row['category']: row['count']
            for row in GuardrailEvent.objects.values('category').annotate(count=Count('id'))
        }
        guardrail_by_action = {
            row['action']: row['count']
            for row in GuardrailEvent.objects.values('action').annotate(count=Count('id'))
        }

        return Response({
            'total_members': total_members,
            'active_members': active_members,
            'suspended_members': suspended_members,
            'banned_members': banned_members,
            'total_sessions': total_sessions,
            'active_users': active_users,
            'total_reports': total_reports,
            'error_count': error_24h,
            # 비용/AI 호출 데이터 없음
            'ai_calls': 0,
            'monthly_cost': 0,
            'points': {
                'earned': point_summary['earned'] or 0,
                'used': point_summary['used'] or 0,
                'refunded': point_summary['refunded'] or 0,
                'transaction_count': PointHistory.objects.count(),
            },
            'guardrails': {
                'by_category': guardrail_by_category,
                'by_action': guardrail_by_action,
                'event_count': GuardrailEvent.objects.count(),
            },
            'weekly_sessions': weekly_sessions,
            'system_health': {
                'stt_status': 'normal',
                'error_rate_24h': error_rate,
                'audit_count_24h': audit_24h_total,
            },
        })


class MemberDeleteView(AdminAPIView):
    def delete(self, request, member_id):
        if request.user.id == member_id:
            return Response(
                {'detail': '본인 계정은 삭제할 수 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            member = get_object_or_404(User.objects.select_for_update(), id=member_id)
            AuditLog.objects.create(
                actor=request.user,
                action_type='member_delete',
                target_type=User._meta.db_table,
                target_id=str(member.id),
                before_value={'email': member.email, 'name': member.name, 'status': member.status},
                after_value={},
            )
            # 연관 데이터 명시적 삭제 (CASCADE 미설정 항목 포함)
            AnalysisSession.objects.filter(user=member).delete()
            JdAnalysis.objects.filter(user=member).delete()
            InterviewSession.objects.filter(user=member).delete()
            UploadedDocument.objects.filter(user=member).delete()
            CoverLetter.objects.filter(user=member).delete()
            ProjectExperience.objects.filter(user=member).delete()
            ResumeMaster.objects.filter(user=member).delete()
            JobDescription.objects.filter(user=member).delete()
            UserProfile.objects.filter(user=member).delete()
            # 유저 삭제 (나머지 CASCADE 처리)
            member.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class MemberInviteView(AdminAPIView):
    """
    차단(banned)된 회원도 포함해 이메일로 초대.
    - 차단된 이메일: 해당 계정을 active로 재활성화해 재가입 허용
    - 일반 이메일: 신규 초대 처리 (이메일 발송 등 추가 가능)
    """
    def post(self, request):
        serializer = MemberInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        existing = User.objects.filter(email=email).first()
        if existing:
            if existing.status != 'banned':
                return Response(
                    {'detail': '이미 활성 상태인 계정입니다.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                before_status = existing.status
                existing.status = 'active'
                existing.is_verified = False
                existing.save(update_fields=('status', 'is_verified', 'updated_at'))
                AuditLog.objects.create(
                    actor=request.user,
                    action_type='member_invite_reactivate',
                    target_type=User._meta.db_table,
                    target_id=str(existing.id),
                    before_value={'status': before_status},
                    after_value={'status': 'active', 'is_verified': False},
                )
            return Response(
                {'detail': f'{email} 계정이 재활성화되었습니다. 해당 이메일로 재가입이 가능합니다.'},
                status=status.HTTP_200_OK,
            )

        # 신규 초대 (이메일 발송 로직 추가 가능)
        AuditLog.objects.create(
            actor=request.user,
            action_type='member_invite_new',
            target_type='email',
            target_id=email,
            before_value={},
            after_value={'invited_email': email},
        )
        return Response(
            {'detail': f'{email} 로 초대가 발송되었습니다.'},
            status=status.HTTP_200_OK,
        )


class AuditLogListView(AdminAPIView):
    def get(self, request):
        query_serializer = AuditLogQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        audit_logs = AuditLog.objects.select_related('actor').order_by('-created_at')
        if params.get('action_type'):
            audit_logs = audit_logs.filter(action_type=params['action_type'])
        if params.get('actor_id'):
            audit_logs = audit_logs.filter(actor_id=params['actor_id'])

        total = audit_logs.count()
        results = paginate(audit_logs, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': AuditLogSerializer(results, many=True).data,
            }
        )


class AdminPointAdjustView(AdminAPIView):
    def post(self, request, member_id):
        serializer = AdminPointAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = get_object_or_404(User, id=member_id)

        try:
            result = admin_adjust_points(
                user=member,
                amount=serializer.validated_data['amount'],
                reason=serializer.validated_data['reason'],
                actor_id=request.user.id,
                idempotency_key=serializer.validated_data.get('idempotency_key'),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.objects.create(
            actor=request.user,
            action_type='point_admin_adjust',
            target_type=User._meta.db_table,
            target_id=str(member.id),
            before_value={},
            after_value={
                'amount': result.history.amount,
                'balance_after': result.history.balance_after,
                'point_history_id': result.history.id,
                'created': result.created,
            },
        )

        return Response(
            {
                'point_history_id': result.history.id,
                'user_id': member.id,
                'amount': result.history.amount,
                'balance_after': result.history.balance_after,
                'created': result.created,
            },
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class AdminPointHistoryView(AdminAPIView):
    def get(self, request):
        query_serializer = AdminPointHistoryQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        histories = PointHistory.objects.select_related('user').order_by('-created_at', '-id')
        if params.get('user_id'):
            histories = histories.filter(user_id=params['user_id'])
        if params.get('transaction_type'):
            histories = histories.filter(transaction_type=params['transaction_type'])

        total = histories.count()
        results = paginate(histories, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': AdminPointHistorySerializer(results, many=True).data,
            }
        )


class AdminGuardrailEventListView(AdminAPIView):
    def get(self, request):
        query_serializer = AdminGuardrailEventQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        events = GuardrailEvent.objects.select_related('user').order_by('-created_at', '-id')
        if params.get('category'):
            events = events.filter(category=params['category'])
        if params.get('action'):
            events = events.filter(action=params['action'])
        if params.get('user_id'):
            events = events.filter(user_id=params['user_id'])

        total = events.count()
        results = paginate(events, params['page'], params['size'])
        return Response(
            {
                'total': total,
                'page': params['page'],
                'size': params['size'],
                'results': AdminGuardrailEventSerializer(results, many=True).data,
            }
        )
