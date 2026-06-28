from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import PointHistory


class PointHistorySerializer(serializers.ModelSerializer):
    point_history_id = serializers.IntegerField(source="id", read_only=True)

    class Meta:
        model = PointHistory
        fields = (
            "point_history_id",
            "transaction_type",
            "amount",
            "balance_after",
            "reason_code",
            "reference_id",
            "policy_version",
            "description",
            "created_at",
        )


def _page_params(request):
    try:
        page = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(request.query_params.get("size", 20))
    except (TypeError, ValueError):
        size = 20
    return max(page, 1), min(max(size, 1), 100)


class MyPointBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "point_balance": user.point_balance,
                "point_last_updated_at": user.point_last_updated_at,
                "policy_version": "2026.06",
            },
            status=status.HTTP_200_OK,
        )


class MyPointHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        page, size = _page_params(request)
        queryset = PointHistory.objects.filter(user=request.user).order_by("-created_at", "-id")
        total = queryset.count()
        start = (page - 1) * size
        serializer = PointHistorySerializer(queryset[start:start + size], many=True)
        return Response(
            {
                "total": total,
                "page": page,
                "size": size,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
