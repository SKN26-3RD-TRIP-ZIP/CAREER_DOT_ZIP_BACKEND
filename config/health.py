"""헬스체크 (운영 LB / 컨테이너 / 배포 스모크용).

엔드포인트(예시 라우팅 — config/urls.py 패치는 urls.health.patch.md 참고):
  GET /api/v1/health        : (기존 유지) DB 연결 확인 — 하위호환
  GET /api/v1/health/live   : Liveness — 프로세스 생존만. 외부 의존성 없음(항상 200).
  GET /api/v1/health/ready  : Readiness — DB + Cache(Redis) 연결 가능 여부.

응답에 DB Host / Redis Endpoint / Secret / StackTrace / 사용자데이터를 절대 포함하지 않는다.
값은 'ok' / 'error' 같은 상태 토큰만 노출한다.
"""
import uuid

from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """기존 엔드포인트(하위호환). DB 연결만 확인."""

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
            {"status": "ok" if database == "ok" else "degraded", "database": database},
            status=status_code,
        )


class LivenessView(APIView):
    """Liveness — 외부 의존성 없이 프로세스 생존만 보고. ALB/Docker liveness 용."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "alive"}, status=200)


class ReadinessView(APIView):
    """Readiness — DB + Cache(Redis) 연결 가능 여부. 트래픽 투입 전 게이트.

    - 운영(DEBUG=False)에서는 settings.CACHES 가 Redis 이므로 cache set/get 이
      실제 ElastiCache 연결을 검증한다(LocMem 이면 항상 ok).
    - 어떤 값도 영구 저장하지 않으며 TTL 5초의 임시 키만 사용한다.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        database = "ok"
        try:
            connections["default"].ensure_connection()
        except OperationalError:
            database = "error"

        cache_status = "ok"
        try:
            probe_key = f"health:ready:{uuid.uuid4().hex}"
            cache.set(probe_key, "1", 5)
            if cache.get(probe_key) != "1":
                cache_status = "error"
            cache.delete(probe_key)
        except Exception:
            # Redis 연결 실패 등 — 상세/스택은 노출하지 않는다.
            cache_status = "error"

        ok = database == "ok" and cache_status == "ok"
        return Response(
            {
                "status": "ok" if ok else "degraded",
                "database": database,
                "cache": cache_status,
            },
            status=200 if ok else 503,
        )
