"""관리자 회원 상세 조회 (GET /api/v1/admin/members/{member_id}).

읽기 전용 — DB 스키마 변경/migration 없음.
권한: AdminAPIView(IsAdminUserOrRole = is_staff or role=='admin').
"""
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework.response import Response

from apps.report.models import FinalReport
from .views import AdminAPIView

User = get_user_model()


class MemberDetailView(AdminAPIView):
    def get(self, request, member_id):
        member = get_object_or_404(User, id=member_id)
        sessions = member.interview_sessions.all()
        completed = sessions.filter(status='completed')
        latest = sessions.order_by('-created_at').first()
        report_count = FinalReport.objects.filter(session__user=member).count()

        return Response({
            'user_id': member.id,
            'email': member.email,
            'name': member.name,
            'role': member.role,
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
            'latest_interview_at': latest.created_at if latest else None,
        })
