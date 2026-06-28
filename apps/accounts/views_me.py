"""현재 로그인 사용자 조회 (GET /api/v1/auth/me)."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

from apps.input.models import UserProfile


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
        next_path = '/admin/dashboard' if u.is_staff else ('/mypage' if profile_complete else '/profile')
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
            "next_path": next_path,
        })
