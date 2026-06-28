# 운영 환경변수 매트릭스 (Backend)

> 필수=서버 시작에 반드시 필요 / 선택=미설정 시 안전한 기본값.
> "지금": 도메인 무관하게 지금 값 확정 가능. "DOMAIN": 최종 도메인 확정 후.
> 저장 위치 권장: 비밀=GitHub Actions Secrets 또는 AWS SSM Parameter Store/Secrets Manager. 비밀 아님=.env.prod.
> `.env.example` 에는 키 이름만(값 금지). `.env.prod` 는 Git 추적 금지(`.gitignore` 에 이미 포함 확인).

| 변수 | 필수 | 지금/DOMAIN | 비밀 | 저장 위치 | 비고/상태 |
|---|---|---|---|---|---|
| DEBUG | 필수 | 지금 | 아니오 | .env.prod | 운영 **False**. |
| SECRET_KEY | 필수 | 지금 | 예 | Secrets/SSM | 비우면 부팅 실패. 신규 난수. |
| DATABASE_URL | 필수 | 지금 | 예 | Secrets/SSM | `mysql://…`. 미설정 시 sqlite fallback(운영 금지). |
| REDIS_URL | 필수(운영) | 지금 | 예 | Secrets/SSM | DEBUG=False 인데 없으면 **부팅 실패(설계)**. `rediss://…`. |
| REDIS_KEY_PREFIX | 선택 | 지금 | 아니오 | .env.prod | 기본 `careerzip`. |
| DJANGO_ENV | 선택 | 지금 | 아니오 | .env.prod | `production`. |
| OAUTH_EXCHANGE_CODE_TTL_SECONDS | 선택 | 지금 | 아니오 | .env.prod | 기본 120. |
| GOOGLE_OAUTH_CLIENT_ID/SECRET | 필수(소셜) | 지금 | 예 | Secrets/SSM | Redirect URI 는 DOMAIN. |
| KAKAO_OAUTH_CLIENT_ID/SECRET | 필수(소셜) | 지금 | 예 | Secrets/SSM | Redirect URI 는 DOMAIN. |
| EMAIL_BACKEND | 필수(메일) | 지금 | 아니오 | .env.prod | 운영 SMTP backend. |
| EMAIL_HOST/PORT/USE_TLS | 필수(메일) | 지금 | 아니오 | .env.prod | |
| EMAIL_HOST_USER/PASSWORD | 필수(메일) | 지금 | 예 | Secrets/SSM | 앱 비밀번호. |
| DEFAULT_FROM_EMAIL | 선택 | 지금 | 아니오 | .env.prod | |
| ADMIN_NOTIFICATION_EMAIL | 선택 | 지금 | 아니오 | .env.prod | 미설정 시 가입 알림 생략. |
| OPENAI_API_KEY | 필수(LLM) | 지금 | 예 | Secrets/SSM | |
| PINECONE_API_KEY / INDEX_NAME | 필수(검색) | 지금 | 예 | Secrets/SSM | |
| WORKNET_API_KEY / BASE_URL | 선택 | 지금 | 예 | Secrets/SSM | 채용정보. |
| AWS_S3_BUCKET_NAME/REGION | 선택 | 지금 | 아니오 | .env.prod | 설정 시 S3 미디어. |
| AWS_ACCESS_KEY_ID/SECRET | 선택 | 지금 | 예 | Secrets/SSM | **Instance Role 우선**(키 지양). |
| ALLOWED_HOSTS | 필수 | **DOMAIN** | 아니오 | .env.prod | `<api-domain>`. |
| CORS_ALLOWED_ORIGINS | 필수 | **DOMAIN** | 아니오 | .env.prod | `https://<fe-domain>`. |
| CSRF_TRUSTED_ORIGINS | 필수 | **DOMAIN** | 아니오 | .env.prod | fe+api 도메인. |
| FRONTEND_BASE_URL | 필수 | **DOMAIN** | 아니오 | .env.prod | OAuth 302 redirect 기준. |
| GOOGLE_OAUTH_REDIRECT_URI | 필수 | **DOMAIN** | 아니오 | .env.prod | `https://<api>/api/v1/auth/oauth/google/callback`. |
| KAKAO_OAUTH_REDIRECT_URI | 필수 | **DOMAIN** | 아니오 | .env.prod | kakao callback. |
| REFRESH_COOKIE_DOMAIN | 선택 | **DOMAIN** | 아니오 | .env.prod | 교차도메인 시 필요. |
| REFRESH_COOKIE_SECURE / SAMESITE | 필수(HTTPS) | **DOMAIN** | 아니오 | .env.prod | HTTPS 후 True. |
| SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE | 필수(HTTPS) | **DOMAIN** | 아니오 | .env.prod | HTTPS 후 True. |
| SECURE_BEHIND_PROXY / SECURE_SSL_REDIRECT / SECURE_HSTS_* | 선택(HTTPS) | **DOMAIN** | 아니오 | .env.prod | LB TLS 종단 후. |

## Secret Rotation 절차(요약)
1. 새 값 발급(Provider/SMTP/DB) → 2. Secrets/SSM 갱신 → 3. 재배포(앱이 새 값 로드) →
4. 구 값 폐기 → 5. 로그/히스토리에 값 노출 없는지 확인. SECRET_KEY 교체 시 기존 서명 세션/토큰 무효화 영향 고려.
