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
        })
