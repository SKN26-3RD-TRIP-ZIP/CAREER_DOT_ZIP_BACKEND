from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.analysis.models import AnalysisSession, JdAnalysis
from apps.document.models import UploadedDocument
from apps.input.models import CoverLetter, JobDescription, ProjectExperience, ResumeMaster, UserProfile
from apps.interview.models import InterviewSession
from .models import AuditLog

User = get_user_model()

_RELATED_MODELS = [
    AnalysisSession,
    JdAnalysis,
    InterviewSession,
    UploadedDocument,
    CoverLetter,
    ProjectExperience,
    ResumeMaster,
    JobDescription,
    UserProfile,
]


def delete_member_and_data(member_id, actor):
    """회원과 연관 데이터를 원자적으로 삭제한다.

    FK CASCADE가 설정되지 않은 모델을 명시적으로 삭제한다.
    새 모델이 User에 FK를 추가할 때 _RELATED_MODELS에도 추가해야 한다.
    """
    with transaction.atomic():
        member = get_object_or_404(User.objects.select_for_update(), id=member_id)
        AuditLog.objects.create(
            actor=actor,
            action_type='member_delete',
            target_type=User._meta.db_table,
            target_id=str(member.id),
            before_value={'email': member.email, 'name': member.name, 'status': member.status},
            after_value={},
        )
        for model in _RELATED_MODELS:
            model.objects.filter(user=member).delete()
        member.delete()
