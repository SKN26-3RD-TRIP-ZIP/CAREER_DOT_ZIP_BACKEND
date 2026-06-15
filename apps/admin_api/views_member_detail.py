"""관리자 회원 상세 조회/삭제 (GET·DELETE /api/v1/admin/members/{member_id})."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from apps.analysis.models import AnalysisSession, JdAnalysis
from apps.document.models import UploadedDocument
from apps.input.models import CoverLetter, JobDescription, ProjectExperience, ResumeMaster, UserProfile
from apps.interview.models import InterviewSession
from apps.report.models import FinalReport
from .models import AuditLog
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
            AnalysisSession.objects.filter(user=member).delete()
            JdAnalysis.objects.filter(user=member).delete()
            InterviewSession.objects.filter(user=member).delete()
            UploadedDocument.objects.filter(user=member).delete()
            CoverLetter.objects.filter(user=member).delete()
            ProjectExperience.objects.filter(user=member).delete()
            ResumeMaster.objects.filter(user=member).delete()
            JobDescription.objects.filter(user=member).delete()
            UserProfile.objects.filter(user=member).delete()
            member.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
