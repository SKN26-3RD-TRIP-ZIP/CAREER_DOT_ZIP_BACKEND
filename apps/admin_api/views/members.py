from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.accounts.models import PointHistory
from apps.report.models import FinalReport
from ..serializers import (
    MemberInviteSerializer,
    MemberListQuerySerializer,
    MemberListSerializer,
    MemberStatusSerializer,
)
from ..services import (
    build_member_stats,
    change_member_status,
    invite_or_reactivate_member,
    withdraw_member,
)
from .base import AdminAPIView, paginate

User = get_user_model()


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
        return Response({
            'total': total,
            'page': params['page'],
            'size': params['size'],
            'results': MemberListSerializer(results, many=True).data,
        })


class MemberDetailView(AdminAPIView):
    def get(self, request, member_id):
        member = get_object_or_404(User, id=member_id)
        sessions = member.interview_sessions.all()
        completed = sessions.filter(status='completed')
        latest = sessions.order_by('-created_at').first()
        report_count = FinalReport.objects.filter(session__user=member).count()
        recent_points = PointHistory.objects.filter(user=member).order_by('-created_at', '-id')[:10]

        return Response({
            'user_id': member.id,
            'email': member.email,
            'name': member.name,
            'status': member.status,
            'is_active': member.is_active,
            'is_verified': member.is_verified,
            'is_staff': member.is_staff,
            'created_at': member.created_at,
            'last_login': member.last_login,
            'practice_count': completed.count(),
            'interview_count': sessions.count(),
            'completed_interview_count': completed.count(),
            'report_count': report_count,
            'point_balance': member.point_balance,
            'point_last_updated_at': member.point_last_updated_at,
            'point_histories': [
                {
                    'point_history_id': history.id,
                    'transaction_type': history.transaction_type,
                    'amount': history.amount,
                    'balance_after': history.balance_after,
                    'reason_code': history.reason_code,
                    'created_at': history.created_at,
                }
                for history in recent_points
            ],
            'latest_interview_at': latest.created_at if latest else None,
        })

    def delete(self, request, member_id):
        """회원 탈퇴(소프트 삭제). 개인정보는 보관 기간 경과 후 별도 배치에서 익명화된다."""
        if request.user.id == member_id:
            return Response(
                {'detail': '본인 계정은 탈퇴 처리할 수 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        member = withdraw_member(member_id, request.user)
        if member is None:
            return Response(
                {'detail': '이미 탈퇴한 회원입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


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

        member = change_member_status(member_id, new_status, request.user)
        return Response({
            'id': member.id,
            'status': member.status,
            'updated_at': member.updated_at,
        })


class MemberStatsView(AdminAPIView):
    def get(self, request):
        return Response(build_member_stats())


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

        kind, _ = invite_or_reactivate_member(email, request.user)
        if kind == 'conflict':
            return Response(
                {'detail': '이미 활성 상태인 계정입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if kind == 'reactivated':
            return Response(
                {'detail': f'{email} 계정이 재활성화되었습니다. 해당 이메일로 재가입이 가능합니다.'},
                status=status.HTTP_200_OK,
            )
        return Response(
            {'detail': f'{email} 로 초대가 발송되었습니다.'},
            status=status.HTTP_200_OK,
        )
