"""현재 로그인 사용자 조회 (GET /api/v1/auth/me)."""
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

from apps.input.models import UserProfile

CURRENT_ONBOARDING_VERSION = 1


def build_onboarding_state(user):
    completed_at = user.onboarding_completed_at
    required = (
        not user.is_staff and
        (
            completed_at is None or
            user.onboarding_version < CURRENT_ONBOARDING_VERSION
        )
    )
    return {
        "required": required,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "version": user.onboarding_version,
        "next_path": "/input/onboarding/1" if required else None,
    }


class MeView(APIView):
    """access token 의 사용자 정보를 반환한다. 화면 표시 사용자의 단일 출처."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        u = request.user
        profile = UserProfile.objects.filter(user=u).first()
        profile_complete = bool(
            profile and
            profile.career_type and
            profile.major_type and
            profile.desired_job
        )
        onboarding = build_onboarding_state(u)
        next_path = (
            '/admin/dashboard'
            if u.is_staff
            else (
                onboarding["next_path"]
                if onboarding["required"]
                else ('/mypage' if profile_complete else '/profile')
            )
        )
        return Response({
            "user_id": u.id,
            "email": u.email,
            "name": u.name,
            "is_staff": u.is_staff,
            "is_verified": u.is_verified,
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "profile": {
                "exists": profile is not None,
                "is_complete": profile_complete,
                "profile_id": str(profile.id) if profile else None,
            },
            "onboarding": onboarding,
            "next_path": next_path,
        })


class OnboardingCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.onboarding_completed_at is None or user.onboarding_version < CURRENT_ONBOARDING_VERSION:
            user.onboarding_completed_at = timezone.now()
            user.onboarding_version = CURRENT_ONBOARDING_VERSION
            user.save(update_fields=["onboarding_completed_at", "onboarding_version", "updated_at"])

        return Response({
            "detail": "온보딩이 완료되었습니다.",
            "onboarding": build_onboarding_state(user),
        })
