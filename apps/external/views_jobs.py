"""
Mock 채용공고 API View.

엔드포인트:
- GET /api/v1/external/jobs            목록 + 검색/필터/페이징/정렬
- GET /api/v1/external/jobs/<job_id>   상세

View 는 JobProvider 추상 인터페이스에만 의존한다(사람인 승인 시 서비스 레이어만 교체).
응답에는 source(="MOCK")가 포함되어 프론트에서 Mock 여부를 식별할 수 있다.
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .services.job_provider import get_job_provider


def _parse_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class MockJobListView(APIView):
    """채용공고 목록 (검색/필터/페이징/정렬)."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        filters = {
            "q": params.get("q"),
            "company": params.get("company"),
            "position": params.get("position"),
            "tech": params.get("tech"),
            "region": params.get("region"),
            "career_type": params.get("career_type"),
            "employment_type": params.get("employment_type"),
        }
        sort = params.get("sort", "latest")
        page = _parse_int(params.get("page", 1), 1)
        size = _parse_int(params.get("size", 10), 10)

        provider = get_job_provider()
        result = provider.list_jobs(filters=filters, sort=sort, page=page, size=size)
        return Response(result, status=status.HTTP_200_OK)


class MockJobDetailView(APIView):
    """채용공고 상세."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        provider = get_job_provider()
        job = provider.get_job(job_id)
        if job is None:
            return Response(
                {"detail": "해당 채용공고를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(job, status=status.HTTP_200_OK)
