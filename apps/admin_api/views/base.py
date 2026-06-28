from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..permissions import IsAdminUserOrRole


def paginate(queryset, page, size):
    start = (page - 1) * size
    return queryset[start:start + size]


class AdminAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserOrRole]
