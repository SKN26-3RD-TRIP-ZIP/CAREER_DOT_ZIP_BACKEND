# AWS 배포 설계 및 검증

> 기준: BE develop `d1f8d17` / FE develop `918f771` · 작성일 2026-06-14
> 본 문서는 현재 저장소의 Docker/CI/설정 파일을 분석한 **설계서 + 검증 결과**입니다.
> 실제 자격증명은 적지 않고 **키 이름만** 표기합니다. 코드/DB는 변경하지 않았습니다.

## 1. 배포 목표
- 최종 발표 시연이 가능한 수준으로 백엔드(Django REST) + 프론트(React/Vite) 를 AWS(EC2 단일 인스턴스 + Docker) 에 배포.
- DB는 외부 관리형(MySQL, 예: Aiven) 사용. 정적/미디어는 단일 서버 기준.
- 무중단/오토스케일 등 고가용성은 이번 범위 밖(발표용 단일 노드).

## 2. 현재 배포 준비 상태 (요약)
| 구성요소 | 상태 | 비고 |
|---|---|---|
| BE Dockerfile | ✅ 존재 | `python:3.10-slim`, ffmpeg/libpq/build-essential, **CMD = `runserver`(개발용)** |
| BE 프로덕션 WSGI(gunicorn) | ⚠️ 부분 | `gunicorn` requirements 에 있으나 Dockerfile CMD 미적용 |
| FE Dockerfile(dev) | ✅ 존재 | `npm run dev` |
| FE Dockerfile.prod(멀티스테이지→nginx) | 🟥 **주석 처리됨** | 내용은 설계돼 있으나 비활성 |
| nginx.conf | 🟥 **주석 처리됨** | SPA fallback + `/api/`→`backend:8000` 프록시 설계 존재(비활성) |
| docker-compose.yml / docker-compose.prod.yml | 🟥 **없음** | deploy 워크플로우가 `docker-compose.prod.yml`을 참조하나 파일 부재 |
| GitHub Actions ci.yml / deploy.yml | 🟥 **전체 주석 처리됨** | 설계만 존재, 비활성. monorepo `./backend`,`./frontend` 경로 가정 |
| 프로덕션 settings | 🟥 **불일치** | 활성=`config/settings.py`(DEBUG=True, sqlite fallback). orphan `config/settings/base.py`(prod 지향이나 앱 누락·미사용) |
| .env.example | ✅ BE/FE 모두 키 목록 정비됨 | 값 없이 키만 |
| HTTPS/SSL | 🟥 없음 | 인증서/리다이렉트 설정 없음 |
| S3 미디어 | 🟥 없음 | 로컬 `MEDIA_ROOT`(컨테이너 재시작 시 업로드 유실 위험) |

→ **결론: 자동(원클릭) 배포는 BLOCKED.** 수동 EC2+Docker 배포는 아래 보완 작업 후 가능.

## 3. 서버 구성 (제안)
```
[사용자] ──HTTPS──> [EC2: Nginx(리버스 프록시)]
                      ├── /            → 프론트 정적(빌드 결과, nginx serve)
                      └── /api/        → 백엔드(gunicorn:8000)
[EC2] ──TLS──> [관리형 MySQL(Aiven 등) : DATABASE_URL]
(선택) [S3] ← 업로드 미디어 보존
```
- 단일 EC2(t3.small 이상 권장 — ffmpeg/Whisper, kiwipiepy 메모리 고려).
- Docker Compose 로 backend / frontend(nginx) 컨테이너 구동.

## 4. 프론트 배포 방식
- 권장: `Dockerfile.prod`(멀티스테이지: node 빌드 → `nginx:alpine` 서빙) **주석 해제 후 사용**.
- `nginx.conf` 주석 해제: SPA fallback(`try_files ... /index.html`) + `/api/` 프록시.
- 빌드 시 `VITE_API_BASE_URL` 주입(빌드 타임 환경변수). 예: `https://<도메인>/api/v1`.
- 산출물 `dist/` 는 이미지에만 포함, **레포 커밋 금지**.

## 5. 백엔드 배포 방식
- 프로덕션은 `runserver` 대신 **gunicorn** 사용 권장:
  - 예) `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3`
  - Dockerfile CMD 를 prod용으로 분기(또는 compose 의 command 로 오버라이드).
- `collectstatic` 수행(STATIC_ROOT) 후 nginx 또는 whitenoise 로 정적 제공.
- 마이그레이션: 컨테이너 기동 시 `python manage.py migrate` 선행.

## 6. Nginx Reverse Proxy 설계
- `location /` → 프론트 정적(index.html fallback).
- `location /api/` → `proxy_pass http://backend:8000;` (+ `X-Forwarded-*`, `Host`).
- (배포 시) `client_max_body_size 10m;` 추가 권장 — 파일 업로드 10MB 제한과 정합.
- HTTPS: certbot(Let's Encrypt) 또는 ALB+ACM 으로 TLS 종단.

## 7. Docker 실행 방식
- 현재 개발: `docker build` 후 BE `runserver`, FE `npm run dev`.
- 배포(제안): `docker-compose.prod.yml`(신규 작성 필요)로 backend(gunicorn)+frontend(nginx) 동시 기동.
- compose 파일이 **없으므로 신규 작성이 선행**되어야 함(§14 BLOCKED).

## 8. 환경변수 목록 (키 이름만)
**Backend (.env)**
```
DJANGO_ENV=***            # local | prod
DEBUG=***
ALLOWED_HOSTS=***
SECRET_KEY=***
DATABASE_URL=***          # mysql://... (관리형)
CORS_ALLOWED_ORIGINS=***  # prod 화이트리스트
OPENAI_API_KEY=***
INTERVIEW_AI_CHAIN_ENGINE=***
INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=***
PINECONE_API_KEY=***
PINECONE_INDEX_NAME=***
WORKNET_API_KEY=***
WORKNET_BASE_URL=***
EMAIL_BACKEND=***
EMAIL_HOST=***
EMAIL_PORT=***
EMAIL_HOST_USER=***
EMAIL_HOST_PASSWORD=***
EMAIL_USE_TLS=***
DEFAULT_FROM_EMAIL=***
ADMIN_NOTIFICATION_EMAIL=***
FRONTEND_BASE_URL=***
EMAIL_VERIFICATION_TOKEN_MAX_AGE=***
# (선택) REDIS_URL=***
```
**Frontend (.env / 빌드 타임)**
```
VITE_API_BASE_URL=***     # 예: https://<도메인>/api/v1
```
> 실제 값은 `.env`(미커밋) 또는 GitHub Secrets/EC2 서버에만 보관. `.env.example` 에는 키 이름만.

## 9. DB 연결 방식
- `dj_database_url` 로 `DATABASE_URL` 파싱. MySQL 사용 시 `mysqlclient`/`pymysql` 의존.
- 활성 `config/settings.py`: `DATABASE_URL` 없으면 **sqlite fallback**(로컬/테스트용). 운영에서는 반드시 `DATABASE_URL`(MySQL) 주입.
- (Aiven 등) SSL 필요 시 옵션 처리 로직 존재(settings.py 의 ssl 변환). prod 에서 SSL require 검토.

## 10. 정적 파일 / 미디어 파일 처리
- STATIC: `STATIC_URL=/static/`, prod 는 `collectstatic` → nginx 서빙 권장.
- MEDIA: 현재 **로컬 디스크**(`MEDIA_ROOT=BASE_DIR/media`). 컨테이너 재시작/다중 인스턴스 시 업로드 유실 → **S3 + django-storages 도입은 추후 확장**(이번 보류).
- 발표용 단일 노드에서는 로컬 미디어로 시연 가능(볼륨 마운트로 영속화 권장).

## 11. GitHub Actions 배포 흐름 (현재 설계 / 비활성)
- `ci.yml`: develop/main PR 시 Docker 빌드 + `manage.py test` (전체 주석).
- `deploy.yml`: main push/수동 → DockerHub 빌드·푸시 → EC2 SSH(`appleboy/ssh-action`) → `docker compose -f docker-compose.prod.yml pull && up -d` (전체 주석).
- 전제 Secrets: `DOCKERHUB_USERNAME/TOKEN`, `EC2_HOST/USER/SSH_KEY`, `DATABASE_URL`.
- ⚠️ 워크플로우가 `./backend`,`./frontend` (monorepo) 와 `docker-compose.prod.yml` 을 가정 → 현재 **분리 레포 구조 + compose 부재**와 불일치(수정 필요).

## 12. 배포 순서 (수동 기준, 보완 후)
1. EC2 준비(Docker, docker compose 설치), 보안그룹(80/443) 개방.
2. 관리형 MySQL 생성 + `DATABASE_URL` 확보.
3. 서버에 `.env`(BE), FE 빌드용 `VITE_API_BASE_URL` 준비.
4. `Dockerfile.prod`/`nginx.conf` 주석 해제, `docker-compose.prod.yml` 작성, BE CMD gunicorn 적용.
5. `docker compose -f docker-compose.prod.yml up -d --build`.
6. `migrate` + `collectstatic` 실행.
7. (HTTPS) certbot 발급/적용.
8. 스모크 테스트(아래 §15).

## 13. 롤백 방법
- 이미지 태그 기반: 직전 정상 태그로 `docker compose pull && up -d`.
- 또는 직전 커밋으로 체크아웃 후 재빌드.
- DB 마이그레이션 롤백은 위험 → 발표 전에는 스키마 변경 배포 지양(이번 작업 DB 변경 없음).

## 14. 현재 BLOCKED 항목
1. `docker-compose.yml` / `docker-compose.prod.yml` 부재 → 작성 필요.
2. FE `Dockerfile.prod`, `nginx.conf` 주석 처리 → 해제/검증 필요.
3. BE Dockerfile `runserver` → prod **gunicorn** 전환 필요.
4. 프로덕션 settings 불일치(`settings.py` DEBUG=True / orphan `settings/base.py` 앱 누락) → **prod 설정 정리 필요**(DB 변경 아님, 설정 리팩터링 — 별도 PR 권장).
5. CI/CD 워크플로우 전체 주석 + 경로/compose 불일치 → 활성화 전 수정 필요.
6. HTTPS/SSL 미설정.
7. 미디어 로컬 저장(영속성/확장성) — S3 추후.
8. `SECRET_KEY` 기본값(insecure) 하드코딩 → prod 는 env 주입 필수.
> 위 항목은 **코드/DB 변경 없이 설정·인프라 작업**이며, 발표 시연은 로컬/개발 서버로 가능. 실배포는 보완 후 권장.

## 15. 최종 배포 전 체크리스트
- [ ] `DATABASE_URL`(MySQL) 연결 확인 + `migrate` 성공
- [ ] `SECRET_KEY`/`DEBUG=False`/`ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS` prod 값 주입
- [ ] BE gunicorn 구동, `/api/v1/...` 200 응답
- [ ] FE 빌드 + nginx SPA fallback + `/api` 프록시 동작
- [ ] 파일 업로드(10MB, `client_max_body_size`) 정상
- [ ] 이메일 SMTP(tripdotzip) 실제 발송 확인
- [ ] HTTPS 적용, http→https 리다이렉트
- [ ] `.env`/Secrets 미커밋 확인, `dist`/`node_modules` 미포함
- [ ] 스모크: 회원가입→인증→로그인→면접→리포트 1회 통과
