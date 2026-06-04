"""
Django 기본 설정 파일
환경 분기: DJANGO_ENV 환경변수로 local / prod 구분
"""

import os
import sys
import dj_database_url

# ===== 환경 구분 =====
DJANGO_ENV = os.environ.get("DJANGO_ENV", "local")

# ===== 필수 환경변수 체크 (없으면 명확한 에러 출력 후 종료) =====
_REQUIRED_ENV_VARS = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL", "OPENAI_API_KEY"]
_missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
if _missing:
    print(
        f"[ERROR] 필수 환경변수가 설정되지 않았습니다: {', '.join(_missing)}\n"
        f"        .env.local 또는 .env.prod 파일을 확인하세요.",
        file=sys.stderr,
    )
    sys.exit(1)

# ===== 기본 설정 =====
SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = DJANGO_ENV != "prod"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ===== 앱 목록 =====
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 서드파티
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    # 로컬 앱
    "apps.accounts",
    "apps.admin_panel",
    "apps.analysis",
    "apps.evaluation",
    "apps.input",
    "apps.interview",
    "apps.prepare",
]

# ===== 미들웨어 (CorsMiddleware는 반드시 맨 위에 위치) =====
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # "django.middleware.csrf.CsrfViewMiddleware",       # JWT 인증 방식에서는 불필요 (DRF가 우회 처리)
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # "django.contrib.messages.middleware.MessageMiddleware",  # API 서버에서는 사용 안 함
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ===== 데이터베이스 (Aiven 외부 PostgreSQL) =====
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL"),
        conn_max_age=600,
        # ssl_require=DJANGO_ENV == "prod",  # [배포 준비 전 주석 처리] 배포 시 활성화
    )
}

# ===== Redis 캐시 (세션 + 폴링 태스크 상태) — Redis 준비 전 주석 처리 =====
# CACHES = {
#     "default": {
#         "BACKEND": "django_redis.cache.RedisCache",
#         "LOCATION": os.environ.get("REDIS_URL", "redis://redis:6379/0"),
#         "OPTIONS": {
#             "CLIENT_CLASS": "django_redis.client.DefaultClient",
#         },
#     }
# }

# ===== 세션: Redis 캐시 백엔드 사용 — Redis 준비 전 주석 처리 =====
# SESSION_ENGINE = "django.contrib.sessions.backends.cache"
# SESSION_CACHE_ALIAS = "default"

# ===== CORS 설정 =====
# [배포 준비 전] 로컬 개발 중에는 전체 허용으로 고정
CORS_ALLOW_ALL_ORIGINS = True

# [배포 준비 전 — 아래 블록 주석 처리]
# 배포 시에는 위 CORS_ALLOW_ALL_ORIGINS 줄을 삭제하고 아래 블록을 활성화하세요
# if DJANGO_ENV == "local":
#     CORS_ALLOW_ALL_ORIGINS = True
# else:  # prod
#     CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")

# ===== DRF 설정 =====
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

# ===== JWT 토큰 설정 =====
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# ===== 비밀번호 검증 =====
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ===== 국제화 =====
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# ===== 정적 파일 =====
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
