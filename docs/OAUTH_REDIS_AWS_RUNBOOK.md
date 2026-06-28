# OAuth 공유 캐시(Redis) · AWS 운영 설정 런북

> 범위: OAuth 일회용 교환 코드의 **Redis 공유 캐시** 적용 + 운영(AWS) 환경변수/보안 설정 정리.
> 원칙: 실제 도메인/Secret 은 기록하지 않는다. 도메인 미확정 항목은 `확인 필요` 로 표기.
> 코드/DB 변경 없음(Migration 0건). 캐시는 Django Cache 추상화만 사용.

## 1. 코드 변경 요약 (feature/oauth-redis-production-readiness)
- `config/settings.py`
  - `CACHES` 추가: `REDIS_URL` 있으면 `django_redis.cache.RedisCache`, 테스트는 LocMem, 로컬(DEBUG)·REDIS 없음은 LocMem, **운영(DEBUG=False)+REDIS_URL 없음이면 `ImproperlyConfigured` 로 부팅 실패(조용한 LocMem 대체 금지)**.
  - `IGNORE_EXCEPTIONS=False` (교환 코드는 1회성/짧은 TTL — Redis 오류를 숨기지 않음).
  - 운영 HTTPS 보안 플래그(모두 env-gated, 기본 off): `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_BEHIND_PROXY`(→`SECURE_PROXY_SSL_HEADER`), `SECURE_SSL_REDIRECT`, `SECURE_HSTS_*`.
- `requirements.txt`: `redis==5.0.8`, `django-redis==5.4.0` 활성화.
- `.env.example`: `REDIS_URL`, `REDIS_KEY_PREFIX`, 위 보안 플래그 문서화(값 없음).
- 교환 코드 단일 사용 로직(`apps/accounts/services/oauth.py`)은 **변경 없음**. Redis `DEL` 이 원자적이라 `if not cache.delete(key)` 가드가 다중 worker 에서도 1회 소비를 보장.

## 2. 동작 매트릭스
| 환경 | REDIS_URL | 결과 |
|---|---|---|
| 테스트(`manage.py test`/pytest) | 무관 | LocMemCache (외부 Redis 불필요) |
| 로컬 개발(DEBUG=True) | 없음 | LocMemCache |
| 로컬/스테이징 | 있음 | RedisCache |
| 운영(DEBUG=False) | 있음 | RedisCache |
| 운영(DEBUG=False) | **없음** | **부팅 실패(ImproperlyConfigured)** |

## 3. AWS ElastiCache (Redis/Valkey) 요구사항
실제 리소스 생성 권한이 없으므로 **설정 명세만** 제시한다(생성은 인프라 담당이 수행).

- **리소스**: ElastiCache for Redis(또는 Valkey) — 발표/단일노드 기준 `cache.t4g.micro` 1 노드로 충분. 고가용성 필요 시 Multi-AZ.
- **네트워크**: EC2(앱)와 **동일 VPC**. ElastiCache 는 프라이빗 서브넷에 배치(퍼블릭 노출 금지).
- **Security Group**:
  - ElastiCache SG: **inbound TCP 6379** 를 **EC2 앱 SG 출처로만** 허용(0.0.0.0/0 금지).
  - EC2 앱 SG: outbound 6379 → ElastiCache SG 허용.
- **포트**: 6379 (Redis 기본).
- **TLS**: ElastiCache `in-transit encryption` 사용 시 `REDIS_URL=rediss://...`(s 2개). 미사용 시 `redis://...`. AUTH token 사용 시 `rediss://:<token>@host:6379/0` (token 은 `.env.prod`/Secrets 에만).
- **REDIS_URL 형식**:
  - 평문: `redis://<primary-endpoint>:6379/0`
  - TLS: `rediss://<primary-endpoint>:6379/0`
  - TLS+AUTH: `rediss://:<auth-token>@<primary-endpoint>:6379/0`
- **운영 환경변수 주입 위치**: EC2 의 `.env.prod`(미커밋) 또는 `docker-compose.prod.yml` 의 `env_file`/`environment`, 또는 GitHub Actions Secrets → 배포 시 주입. `.env.example` 에는 키 이름만.
- **연결 확인 명령**(EC2 또는 앱 컨테이너 내부):
  ```bash
  # redis-cli (TLS 면 --tls)
  redis-cli -h <primary-endpoint> -p 6379 [--tls] ping        # → PONG
  # Django 캐시 경유 확인
  python manage.py shell -c "from django.core.cache import cache; cache.set('k','v',10); print(cache.get('k'))"  # → v
  ```
- **장애 시 확인 로그**: gunicorn/Django stderr 의 `redis.exceptions.ConnectionError`, ElastiCache CloudWatch(`CurrConnections`, `Evictions`, CPU), SG 인바운드 6379 규칙, 서브넷 라우팅.

## 4. 운영 환경변수 (도메인 무관 / 도메인 필요 분리)
> 도메인 미확정이므로 도메인 의존 값은 `확인 필요`. 실제 값은 `.env.prod`/Secrets 에만.

### 도메인 무관 (지금 확정 가능)
```
DEBUG=False
SECRET_KEY=***(Secrets)
DATABASE_URL=***(관리형 MySQL, Secrets)
REDIS_URL=***(ElastiCache 엔드포인트)
REDIS_KEY_PREFIX=careerzip
OAUTH_EXCHANGE_CODE_TTL_SECONDS=120          # 기존 정책 유지
GOOGLE_OAUTH_CLIENT_ID / SECRET=***(Secrets)
KAKAO_OAUTH_CLIENT_ID / SECRET=***(Secrets)
FRONTEND_OAUTH_CALLBACK_PATH=/oauth/callback
```
### 도메인 필요 (확인 필요 — 최종 도메인 확정 후)
```
ALLOWED_HOSTS=<api 도메인>                     # 확인 필요
CORS_ALLOWED_ORIGINS=https://<frontend 도메인> # 확인 필요
CSRF_TRUSTED_ORIGINS=https://<frontend 도메인>,https://<api 도메인>  # 확인 필요
FRONTEND_BASE_URL=https://<frontend 도메인>    # 확인 필요
GOOGLE_OAUTH_REDIRECT_URI=https://<api 도메인>/api/v1/auth/oauth/google/callback  # 확인 필요
KAKAO_OAUTH_REDIRECT_URI=https://<api 도메인>/api/v1/auth/oauth/kakao/callback    # 확인 필요
REFRESH_COOKIE_SECURE=True
REFRESH_COOKIE_SAMESITE=Lax(동일 사이트) | None(교차 도메인)   # 배포 구조에 따라
REFRESH_COOKIE_DOMAIN=<공통 상위 도메인 또는 미설정>           # 확인 필요
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_BEHIND_PROXY=True        # LB/nginx TLS 종단 시
SECURE_SSL_REDIRECT=True        # nginx 가 처리하지 않을 때만
```
### Frontend (빌드 타임)
```
VITE_API_BASE_URL=https://<api 도메인>/api/v1   # 확인 필요
VITE_GOOGLE_OAUTH_ENABLED=true
VITE_KAKAO_OAUTH_ENABLED=true
```

## 5. Provider 콘솔 (운영 — 확인 필요)
> 현재 로컬 redirect 는 동작 확인됨. 운영 URL 은 도메인 확정 후 추가 등록(기존 로컬 항목 유지).

- **Google**
  - Authorized JavaScript origin: `https://<frontend 도메인>`  (확인 필요)
  - Authorized redirect URI: `https://<api 도메인>/api/v1/auth/oauth/google/callback`  (확인 필요)
- **Kakao**
  - 사이트 도메인: `https://<frontend 도메인>`, `https://<api 도메인>`  (확인 필요)
  - Redirect URI: `https://<api 도메인>/api/v1/auth/oauth/kakao/callback`  (확인 필요)

## 6. 다중 worker 공유 검증 (운영/스테이징)
gunicorn `--workers 3` 환경에서:
```
worker A: 소셜 로그인 → callback 이 일회용 code 발급(Redis 저장)
worker B: /auth/oauth/exchange 요청이 다른 worker 로 라우팅돼도 동일 code 교환 성공
2차 교환: OAUTH_EXCHANGE_CODE_USED (단일 사용)
TTL 경과: OAUTH_EXCHANGE_CODE_EXPIRED
```
> LocMemCache 였다면 worker B 가 code 를 못 찾아 실패 → Redis 적용으로 해소.
> 자동 단위검증(`test_oauth_redis_cache.py`)은 캐시 백엔드 비의존(단일 사용/만료/위조/Key·Value 안전).
> **실제 다중 프로세스 + 실 Redis 공유 검증은 ENV_REQUIRED**(운영/스테이징 Redis 필요).

## 7. 보안 점검 (캐시 관련)
- Cache **Value**: `{user_id, provider, next_path, created, needs_terms}` 만 저장. 이메일·access/refresh·Provider 토큰 미포함.
- Cache **Key**: `careerzip:oauth:exchange:<무작위 jti>` — 이메일/토큰 미포함.
- callback URL: 성공은 `?code=<jti 서명토큰>`, 실패는 `?error=<CODE>` 만. JWT/Provider 토큰/상세 미노출.
- TLS: 운영 Redis 는 `rediss://` 권장. AUTH token 은 Secrets 로만.
