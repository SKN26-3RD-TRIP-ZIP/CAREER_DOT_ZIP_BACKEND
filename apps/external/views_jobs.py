"""Mock job API views."""

import json

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.input.models import JobDescription

from .services.job_provider import get_job_provider
from .services.mock_jobs_service import SOURCE, build_job_jd_text


def _parse_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class MockJobListView(APIView):
    """Synthetic job list with search/filter/pagination/sorting."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        filters = {
            "keyword": params.get("keyword"),
            "q": params.get("q"),
            "company": params.get("company"),
            "position": params.get("position"),
            "tech_stack": params.get("tech_stack"),
            "tech": params.get("tech"),
            "location": params.get("location"),
            "region": params.get("region"),
            "career_type": params.get("career_type"),
            "employment_type": params.get("employment_type"),
        }
        sort = params.get("ordering") or params.get("sort") or "latest"
        page = _parse_int(params.get("page", 1), 1)
        size = _parse_int(params.get("size", 10), 10)

        provider = get_job_provider()
        result = provider.list_jobs(filters=filters, sort=sort, page=page, size=size)
        return Response(result, status=status.HTTP_200_OK)


class MockJobDetailView(APIView):
    """Synthetic job detail."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        provider = get_job_provider()
        job = provider.get_job(job_id)
        if job is None:
            return Response(
                {"detail": "Job not found.", "code": "MOCK_JOB_NOT_FOUND"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(job, status=status.HTTP_200_OK)


class MockJobSaveAsJdView(APIView):
    """Create a user-owned JD from a selected synthetic job."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        provider = get_job_provider()
        job = provider.get_job(job_id)
        if job is None:
            return Response(
                {"detail": "Job not found.", "code": "MOCK_JOB_NOT_FOUND"},
                status=status.HTTP_404_NOT_FOUND,
            )

        jd = JobDescription.objects.create(
            user=request.user,
            company_name=job.get("company_name", "")[:100] or "CAREER_ZIP_MOCK",
            position=job.get("position", "")[:100] or "Synthetic Job",
            original_text=build_job_jd_text(job),
            input_method="TEXT",
            keywords=json.dumps(job.get("keywords", []), ensure_ascii=False),
            job_requirements="\n".join(job.get("requirements", [])),
            analysis_status="PENDING",
        )

        return Response(
            {
                "jd_id": str(jd.id),
                "company_name": jd.company_name,
                "position": jd.position,
                "input_method": jd.input_method,
                "created_at": jd.created_at,
                "source": SOURCE,
                "is_mock": True,
                "job_id": job.get("job_id"),
            },
            status=status.HTTP_201_CREATED,
        )
