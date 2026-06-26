from django.db import connections
from django.db.utils import OperationalError
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        database = "ok"
        try:
            connections["default"].ensure_connection()
        except OperationalError:
            database = "error"

        status_code = 200 if database == "ok" else 503
        return Response(
            {
                "status": "ok" if database == "ok" else "degraded",
                "database": database,
            },
            status=status_code,
        )
