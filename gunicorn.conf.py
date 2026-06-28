"""Gunicorn 운영 설정 — Career.zip Backend.

docker-compose.prod.yml / Dockerfile.prod 에서 다음으로 사용:
    gunicorn config.wsgi:application -c gunicorn.conf.py

설계 메모
- workers: CPU 코어 기반 (2*N+1)을 기본값으로 하되 GUNICORN_WORKERS 로 오버라이드.
  운영 메모리(특히 torch/SBERT/kiwipiepy 로딩)를 고려해 t3.small 급에서는 3 으로 고정 권장.
- threads: LLM/STT 등 I/O 대기가 길어 worker 당 threads 를 둬서 동시성 확보(gthread).
- timeout: LLM/STT 호출이 길어 기본 30s 는 부족 → 120s. (필요 시 GUNICORN_TIMEOUT 로 상향)
- graceful_timeout: 배포 시 진행 중 요청을 끊지 않도록 30s.
- max_requests: 메모리 누수 방어용 worker 자동 재활용(+jitter 로 동시 재시작 방지).
- 로그: access/error 를 stdout/stderr 로 — 컨테이너 표준 로깅 → CloudWatch 수집.
- Redis 공유 캐시 덕분에 worker 가 여러 개여도 OAuth 일회용 코드가 공유된다(settings.CACHES).
"""
import multiprocessing
import os


def _int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
workers = _int("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 3))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")
threads = _int("GUNICORN_THREADS", 4)

timeout = _int("GUNICORN_TIMEOUT", 120)
graceful_timeout = _int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _int("GUNICORN_KEEPALIVE", 5)

max_requests = _int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _int("GUNICORN_MAX_REQUESTS_JITTER", 100)

# stdout/stderr 로 로깅 (컨테이너 표준)
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
# 액세스 로그에 응답시간(%(L)s) 포함, 토큰/쿼리스트링 등 민감정보는 기록하지 않음
access_log_format = '%(h)s %(t)s "%(r)s" %(s)s %(b)s %(L)s'

# 임시 파일을 메모리 기반 경로에 둬 EBS I/O 절감(있으면)
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None
