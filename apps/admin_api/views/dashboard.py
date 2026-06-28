from rest_framework.response import Response

from ..services import build_dashboard_stats
from .base import AdminAPIView


class DashboardStatsView(AdminAPIView):
    def get(self, request):
        return Response(
            build_dashboard_stats(
                start=request.query_params.get('start'),
                end=request.query_params.get('end'),
            )
        )
