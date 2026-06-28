#!/usr/bin/env sh
# Career.zip Backend 운영 엔트리포인트.
# 원칙:
#  - Migration 은 "여러 컨테이너가 동시에" 실행하면 안 된다.
#    => 기본값은 collectstatic 만 수행하고 migrate 는 건너뛴다.
#    => 배포 파이프라인(또는 단일 migrate 잡)에서 RUN_MIGRATIONS=1 로 1회만 실행한다.
#  - 비밀값은 로그로 출력하지 않는다.
set -eu

echo "[entrypoint] DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-config.settings} DEBUG=${DEBUG:-unset}"

# 1) 정적 파일 수집 (WhiteNoise 가 서빙). 실패 시 부팅 중단.
echo "[entrypoint] collectstatic ..."
python manage.py collectstatic --noinput

# 2) Migration: 기본 비활성. 배포 잡에서만 RUN_MIGRATIONS=1 로 1회 실행.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] RUN_MIGRATIONS=1 -> applying migrations (this container only)"
  python manage.py migrate --noinput
else
  echo "[entrypoint] skip migrate (RUN_MIGRATIONS!=1). 배포 잡에서 1회 실행하세요."
fi

# 3) 앱 구동: 인자가 있으면 그대로, 없으면 gunicorn.
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec gunicorn config.wsgi:application -c gunicorn.conf.py
fi
