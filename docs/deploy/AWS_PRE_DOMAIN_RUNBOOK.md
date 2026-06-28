# Career.zip — 도메인 확정 전 AWS 배포 런북 (Pre-Domain)

> 범위: 최종 도메인 없이도 진행 가능한 AWS 인프라 설계·구성·검증 절차.
> 원칙: 실제 엔드포인트/SG ID/계정/Secret 은 적지 않는다(키 이름·형식만). 도메인 의존 값은 `DOMAIN_REQUIRED`.
> 이 문서는 기존 `docs/OAUTH_REDIS_AWS_RUNBOOK.md`(ElastiCache 상세) 와
> `docs/AWS_배포_설계_및_검증.md`(전체 배포 설계) 를 **대체가 아니라 보완**한다. 중복 항목은 참조만 한다.
> 상태 표기: PASS / ENV_REQUIRED(AWS 권한 필요) / DOMAIN_REQUIRED(도메인 확정 필요).

## 0. 확정된 배포 구조 (분석 결과)
- **구조 C — 단일 EC2 + Docker Compose + Nginx(프론트 컨테이너) + 관리형 MySQL + 관리형 Redis.**
- 근거: `deploy.yml`(주석본)이 DockerHub push → EC2 SSH → `docker compose -f docker-compose.prod.yml up -d` 패턴.
  프론트 `Dockerfile.prod`(node 빌드→nginx) + `nginx.conf`(`/api`→`backend:8000` 프록시)가 develop 에 **활성** 상태.
- 외부 관리형: **MySQL(RDS 또는 Aiven)**, **Redis(ElastiCache)**. 둘 다 Compose 컨테이너로 띄우지 않는다.

```
[사용자] ──(80/443)──> [EC2: frontend(nginx)] ──/api/──> [backend(gunicorn:8000)]
                                                   │
                          ┌────────────────────────┼─────────────────────────┐
                     [RDS/관리형 MySQL :3306]   [ElastiCache Redis :6379]   [S3(미디어, 선택)]
```

---
## 1. ElastiCache (Redis/Valkey) — 요약 + SG
> 상세(REDIS_URL 형식, TLS/AUTH, 다중 worker 검증, Key/Value 안전)는 `docs/OAUTH_REDIS_AWS_RUNBOOK.md` 참조.
- **노드 타입(MVP)**: `cache.t4g.micro` 1 노드. 고가용성 필요 시 Multi-AZ + replica 1.
- **네트워크**: EC2 와 동일 VPC, **프라이빗 서브넷**. Public Access **금지**.
- **장애 조치**: 단일 노드(MVP)는 자동 장애 조치 없음 → 노드 장애 시 재생성. Multi-AZ 선택 시 자동 failover.
- **백업**: OAuth 교환 코드는 TTL 120초 단기 데이터 → **영구 백업 불필요**. 스냅샷 비활성으로 비용 절감.
- **TLS**: in-transit encryption 사용 시 `REDIS_URL=rediss://...`. 미사용 확정 근거 있을 때만 `redis://`.
- **상태**: 리소스 생성은 **ENV_REQUIRED**(AWS 권한). 연결 검증 명령은 §7.

## 2. 운영 MySQL (RDS 또는 관리형)
- **위치 판단**: 현 `settings.py` 는 `DATABASE_URL`(dj-database-url) 기반 → RDS/Aiven 모두 호환. EC2 내부 MySQL 비권장(영속성/백업).
- **엔진/문자셋**: MySQL 8.x, `utf8mb4` / `utf8mb4_unicode_ci`. Timezone: 앱은 `USE_TZ=True`(UTC 저장), 표시 `Asia/Seoul`.
- **연결 풀/타임아웃**: `settings.py` 가 `conn_max_age=600` 설정(영속 연결). 추가 풀러 불필요.
- **SSL**: 관리형(Aiven 등) SSL 요구 시 `settings.py` 의 ssl 변환 로직이 처리(`?ssl-mode=REQUIRED` 형태). RDS 는 `rds-ca` 사용 검토.
- **DB 사용자 권한**: 앱 전용 계정에 **해당 스키마 한정** DML/DDL. `SUPER`/전역 권한 금지.
- **Public Access**: **금지**. RDS 는 `Publicly accessible = No`.
- **마이그레이션 정책**: 앱 컨테이너는 `RUN_MIGRATIONS=0`. 배포 시 `--profile migrate` 잡으로 **1회만** 실행(§docker-compose).
- **초기 데이터**: 시드 마이그레이션 존재(`0009_seed_default_point_policies`, `0010_seed_default_terms_documents`) → migrate 시 자동.
- **관리자 계정**: `python manage.py createsuperuser`(대화형) 또는 1회용 잡. 비밀번호는 로그/커밋 금지.
- **DATABASE_URL 형식**: `mysql://<user>:<password>@<host>:3306/<database>`  (실제 값은 Secrets/.env.prod 만)
- **상태**: 리소스 생성 **ENV_REQUIRED**. 마이그레이션 전 **스냅샷 권장**(§6).

## 3. Security Group 매트릭스 (도메인 무관, 지금 확정 가능)
> 실제 SG ID 는 문서에 적지 않는다. 출처는 "보안그룹 참조"로 지정(IP 하드코딩 금지).

| SG | Inbound | Source | 목적 |
|---|---|---|---|
| `sg-ec2-app` | 22/tcp(SSH) | **운영자 고정 IP만** | 관리 접속(상시 개방 금지) |
| `sg-ec2-app` | 80/tcp | ALB SG 또는 0.0.0.0/0(임시) | 프론트 진입(HTTPS 전 임시) |
| `sg-ec2-app` | 443/tcp | ALB SG | HTTPS (DOMAIN_REQUIRED) |
| `sg-rds-mysql` | 3306/tcp | **`sg-ec2-app` 만** | EC2→DB |
| `sg-redis` | 6379/tcp | **`sg-ec2-app` 만** | EC2→Redis |

- gunicorn(8000)은 **외부 직접 노출 금지** — 프론트 nginx 만 프록시. SG 에 8000 inbound 두지 않음.
- RDS/ElastiCache **Public Access 금지**. `0.0.0.0/0` 의 3306/6379 **절대 금지**.
- Outbound: 기본 all 허용에서 점진 축소 검토(최소 443 + DB/Redis 포트).

## 4. IAM 최소 권한
- **EC2 Instance Role 우선**(장기 Access Key 지양). 앱은 Role 로 S3/CloudWatch 접근.
- 정책 분리(최소 권한):
  - S3: 대상 버킷 한정 `s3:GetObject/PutObject/DeleteObject/ListBucket` (와일드카드 `*` 금지).
  - ECR(사용 시): `ecr:GetDownloadUrlForLayer`, `BatchGetImage`, `GetAuthorizationToken`.
  - CloudWatch Logs: `logs:CreateLogStream`, `PutLogEvents` (대상 LogGroup 한정).
  - SSM Parameter Store / Secrets Manager: 해당 경로 **읽기 전용**.
- **AdministratorAccess 금지.** 배포용 CI 자격은 DockerHub/ECR push + (선택)EC2 배포에 필요한 최소만.
- 상태: 실제 Role/정책 생성 **ENV_REQUIRED**.

## 5. S3 (미디어) — 선택
- `settings.py`: `AWS_S3_BUCKET_NAME` 설정 시 자동 S3 스토리지(django-storages). 미설정 시 로컬 `media/`.
- 권장: 업로드 영속성을 위해 S3 사용. **Bucket Public Access Block = ON**, 객체 ACL private, 필요 시 Presigned URL.
- 파일 정책: 업로드 10MB 상한(nginx `client_max_body_size 10m` + DRF). MIME/확장자 검증은 앱 계층 확인 권장.
- 상태: 버킷 생성 **ENV_REQUIRED**. 코드는 env 만 주면 동작(PASS).

## 6. 모니터링 · 백업 · 복구 · 롤백 (도메인 무관)
### 모니터링/알람 (기준값 — 생성은 ENV_REQUIRED)
- App 로그: gunicorn access/error → stdout/stderr → CloudWatch Logs(Agent 또는 awslogs 드라이버). 보존 14~30일.
- 알람 권장 임계:
  - EC2 CPU > 80% (5분), 메모리 > 85%, 디스크 > 80%.
  - ALB/Nginx 5xx 비율 > 1% (5분).
  - RDS: `DatabaseConnections` 급증, `FreeStorageSpace` < 15%, CPU > 80%.
  - ElastiCache: `CurrConnections` 급증, `Evictions` > 0 지속, `DatabaseMemoryUsagePercentage` > 80%.
  - 헬스체크 `/api/v1/health/ready` 실패, 배포 실패.
- 로그 마스킹: 이메일은 이미 앱 로그에서 마스킹(`te***@example.com` 확인됨). JWT/OAuth code/Provider token 은 로그 금지. Request ID 도입은 향후 권장.

### 백업/복구
- RDS: Automated Backup(보존 7일) + **마이그레이션 전 수동 스냅샷**. 복구는 스냅샷→새 인스턴스→`DATABASE_URL` 교체.
- Redis: 단기 데이터 → 백업 불필요(§1).

### 롤백
- 앱: 이미지 태그 보존 → `BACKEND_TAG=<직전 SHA> docker compose up -d backend`.
- 마이그레이션 포함 배포: 역호환(additive) 우선. 파괴적 스키마 변경은 사전 스냅샷 + 점검창 필요.
- 프론트: 직전 `frontend:<SHA>` 이미지로 교체.

## 7. 검증 명령 (EC2/동일 VPC에서 실행 — ENV_REQUIRED)
```bash
# DNS/TCP
getent hosts <redis-endpoint>; nc -vz <redis-endpoint> 6379
getent hosts <db-host>;        nc -vz <db-host> 3306
# Redis (TLS면 --tls)
redis-cli -h <redis-endpoint> -p 6379 [--tls] ping            # => PONG
# Django 캐시 set/get/delete + TTL
python manage.py shell -c "from django.core.cache import cache; cache.set('k','v',5); print(cache.get('k')); cache.delete('k'); print(cache.get('k'))"
# DB
python manage.py check
python manage.py showmigrations
python manage.py migrate --plan
# 헬스
curl -fsS http://localhost:8000/api/v1/health/ready    # {"status":"ok","database":"ok","cache":"ok"}
```
장애 시 점검 순서: SG inbound(6379/3306) → 서브넷 라우팅 → 엔드포인트 DNS → TLS 모드(rediss/ssl) → 앱 로그의 ConnectionError.

## 8. 예상 비용 (MVP, ap-northeast-2, 대략·월)
| 리소스 | 사양 | 대략 |
|---|---|---|
| EC2 | t3.small (2vCPU/2GB) | ~$15–19 |
| EC2 | t3.medium (권장, ffmpeg/SBERT 메모리) | ~$30–38 |
| ElastiCache | cache.t4g.micro 1노드 | ~$11–13 |
| RDS MySQL | db.t4g.micro + 20GB gp3 | ~$15–20 |
| S3 | 소량(수 GB) | ~$1 미만 |
| 데이터 전송 | 소량 | 소액 |
> 절감 옵션: 단일 노드(Redis replica 미사용), RDS 단일 AZ, t3 대신 t4g(arm), 미사용 시 야간 중지(발표 전 상시 가동 권장).
> 정확한 단가는 AWS Pricing 으로 재확인(요율 변동). 위는 자릿수 감각용.

## 9. DOMAIN_REQUIRED (도메인 확정 후에만)
- Route53 DNS, ACM 인증서, ALB 443/HTTPS redirect, nginx `server_name`.
- `.env.prod`: `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `FRONTEND_BASE_URL`,
  `GOOGLE_OAUTH_REDIRECT_URI`, `KAKAO_OAUTH_REDIRECT_URI`, `REFRESH_COOKIE_DOMAIN`,
  `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SECURE_BEHIND_PROXY=True`.
- Frontend 빌드: `VITE_API_BASE_URL=https://<api-domain>/api/v1`.
- Provider 콘솔(운영 등록): Google JS Origin/Redirect URI, Kakao 사이트 도메인/Redirect URI.
- 운영 OAuth E2E(실 도메인 + HTTPS).
