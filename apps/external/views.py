from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.worknet_service import WorknetService


class WorknetJobSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = WorknetService()
        result = service.search_jobs(
            keyword=request.query_params.get('keyword'),
            page=request.query_params.get('page', 1),
            size=request.query_params.get('size', 10),
        )
        return Response(result)
