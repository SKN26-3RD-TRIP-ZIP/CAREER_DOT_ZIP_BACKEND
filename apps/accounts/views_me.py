"""현재 로그인 사용자 조회 (GET /api/v1/auth/me)."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions


class MeView(APIView):
    """access token 의 사용자 정보를 반환한다. 화면 표시 사용자의 단일 출처."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response({
            "user_id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_verified": u.is_verified,
            "is_active": u.is_active,
            "is_staff": u.is_staff,
            # 최근 로그인 일시 (AbstractBaseUser.last_login). 로그인 시 update_last_login 으로 갱신됨.
            # 마이페이지에서 "최근 로그인" 표시에 사용. 미로그인 이력 시 null.
            "last_login": u.last_login.isoformat() if u.last_login else None,
        })
