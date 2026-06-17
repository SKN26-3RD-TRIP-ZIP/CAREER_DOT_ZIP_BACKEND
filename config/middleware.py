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

        return response


def get_avg_response_time():
    times = cache.get(RESPONSE_TIME_CACHE_KEY, [])
    if not times:
        return None
    return round(sum(times) / len(times))
