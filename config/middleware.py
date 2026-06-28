import time
from django.core.cache import cache

RESPONSE_TIME_CACHE_KEY = 'api_response_times'
MAX_SAMPLES = 50


class ResponseTimeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 정적 파일·admin 패널은 제외
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        start = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000)

        times = cache.get(RESPONSE_TIME_CACHE_KEY, [])
        times.append(elapsed_ms)
        if len(times) > MAX_SAMPLES:
            times = times[-MAX_SAMPLES:]
        cache.set(RESPONSE_TIME_CACHE_KEY, times, timeout=3600)

        # 5xx(미처리 예외 포함)는 대시보드 24h 에러 집계용으로 기록한다.
        # 예외는 Django가 500 응답으로 변환해 여기로 돌아오므로 한 곳에서만 잡는다.
        if response.status_code >= 500:
            try:
                from apps.admin_api.models import ApiErrorLog
                ApiErrorLog.objects.create(
                    path=request.path[:255],
                    method=request.method,
                    status_code=response.status_code,
                )
            except Exception:
                pass

        return response


def get_avg_response_time():
    times = cache.get(RESPONSE_TIME_CACHE_KEY, [])
    if not times:
        return None
    return round(sum(times) / len(times))
