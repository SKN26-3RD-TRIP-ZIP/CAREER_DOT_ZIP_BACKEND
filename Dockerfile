FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치
# - build-essential: C 확장 컴파일용
# - libpq-dev: psycopg2 빌드용
# - ffmpeg: OpenAI Whisper STT 오디오 처리용
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    ffmpeg \
    pkg-config \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# 패키지 설치 (캐시 레이어 분리)
COPY requirements.txt .
RUN pip install torch==2.12.0+cpu --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# docker-compose.prod.yml에서 command로 오버라이드하거나, 개발 시 그대로 사용
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
