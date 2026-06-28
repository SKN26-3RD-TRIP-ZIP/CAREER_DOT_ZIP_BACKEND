# Career.zip 실제 데이터 기반 통합 E2E QA 계획서

> 문서 버전: v1.0 · 작성일: 2026-06-10 · 작성: 통합 QA
> 대상 레포: `CAREER_DOT_ZIP_BACKEND` (브랜치 `develop` 기준 분석)
> 관련 문서: 기획서, 설계서, CAREER_ZIP_API명세서_통합본, ERD, Prompt 설계서, AWS 배포 문서, GitHub Actions 문서
> ⚠️ 본 계획은 **문서가 우선 기준**이며, 구현과 문서가 다르면 임의 수정하지 않고 "불일치 항목"으로 기록한다.

---

## 1. 목적

기존 mock 데이터 중심 QA에서 벗어나, 실제 서비스 흐름(회원가입/로그인 → 사용자 입력 → 면접 세션 → 질문/답변 → 평가 → 리포트 → 마이페이지/관리자)을 실제 계정·실제 데이터 기준으로 End-to-End 검증한다.

## 2. 범위

| 구분 | 포함 | 비고 |
|---|---|---|
| 백엔드 API | `/api/v1` 전체 흐름 | 본 QA의 1차 대상 |
| 프론트엔드 | 화면 흐름 / OAuth 로그인 | 레포 미연결 → 수동 체크리스트로 분리 |
| 실제 AI 호출 | 질문/꼬리질문/평가 | 기본 mock, 환경변수 전환 필요 |
| 외부 채용 API | Worknet | 합법 Open API만 사용, 사람인은 미승인 |
| 운영 DB | 직접 수정 금지 | 읽기/QA 식별 데이터만 |

## 3. 분석으로 확인된 현재 아키텍처 (구현 기준)

### 3.1 라우팅 구조 (`config/urls.py`)
- `POST /api/v1/auth/...` → `apps.accounts`
- `/api/v1/interviews/...` → `apps.interview.urls` (**중첩형 RESTful 세션 API**)
- `/api/v1/...` → `apps.interview.mvp_urls` (**MVP 평면형 API — API 명세서가 가리키는 대상**)
- `/api/v1/...` → `apps.input` (JD/프로필/이력서/자소서/프로젝트)
- `/api/v1/...` → `apps.evaluation`, `apps.report`, `apps.document`
- `/api/v1/mypage/...` → `apps.mypage`
- `/api/v1/admin/...` → `apps.prompt`(페르소나/프롬프트) + `apps.admin_api`(회원/audit)
- `/api/v1/external/...` → `apps.external`(Worknet)
- `/api/v1/analysis/...` → `apps.analysis`(JD 분석/매칭 파이프라인)

> **핵심 발견 1 — 면접 API 이중 표면(dual surface)**: 세션/질문/답변 API가
> `interviews/` 중첩형과 평면형 MVP(`/sessions`, `/answers`, `/answers/{id}/stt`, `/answers/{id}/followup`) **두 벌** 존재한다.
> 사용자가 제시한 필수 확인 API 목록은 **MVP 평면형**과 일치한다. QA 기준은 MVP 표면으로 고정하되,
> 두 표면 중 어느 것이 정식인지 **NEEDS_CONFIRMATION**으로 팀 확인이 필요하다.

### 3.2 인증/권한
- 인증: `rest_framework_simplejwt` JWT (`DEFAULT_AUTHENTICATION_CLASSES = JWTAuthentication`), 기본 권한 `IsAuthenticated`.
- 로그인 응답: `access_token`(body) + `refresh_token`(HttpOnly Cookie, `samesite=Lax`, `secure=False`).
- 관리자 권한: `IsAdminUserOrRole` = `is_staff or role=='admin'` (admin_api/prompt 양쪽 적용).
- 사용자 데이터 격리: 조회/수정 시 `session__user=request.user` + `get_object_or_404` 패턴 → 타 사용자 자원 접근 시 **404** 반환(403 아님).

### 3.3 AI 엔진 (mock/real 분기) — `apps/interview/services/ai_chain_engine_factory.py`
- `INTERVIEW_AI_CHAIN_ENGINE` (기본값 `mock`) 로 엔진 선택.
- `mock` → `AIChainMockEngine` (deterministic, LLM 미호출).
- `openai` → `AIChainOpenAIEngine`, 단 `INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=True` 일 때만 실제 호출, 실패 시 **mock fallback**.
- **평가(evaluation)** 는 별도: `apps/evaluation/evaluation_chains.py` 가 `OpenAI` 클라이언트를 직접 사용 → 인터뷰 엔진 플래그와 무관하게 **실제 OpenAI 키 필요**.

### 3.4 데이터/외부 연결 상태
- DB: 현재 `.env` `DATABASE_URL` = **Aiven Cloud MySQL (원격 공유 DB)**, `DJANGO_ENV=local`, `DEBUG=True`. (로컬 `db.sqlite3` 파일도 존재하나 settings는 MySQL 사용.)
- STT: `MVPSTTResultUpdateView` 는 **클라이언트가 보낸 `stt_text` 를 저장**하는 방식. 백엔드에 실제 음성→텍스트 엔진은 없음(프론트/외부 STT 결과 적재용).
- 분석 파이프라인: `apps/analysis` 는 실제 OpenAI 임베딩 + Pinecone RAG 사용. 단 `project_service.py` 의 `extract_projects` / `merge_with_github` / `score_projects` 는 `NotImplementedError`(미구현).
- 외부 채용: `apps/external` Worknet Open API(합법 키 기반). 사람인은 미승인 → 사용 금지. 사용자 직접 입력 JD로 대체.

## 4. mock / real 판정 요약 (상세는 result-template, checklist 참조)

| 영역 | 기본 동작 | real 전환 조건 |
|---|---|---|
| 질문 생성 | **MOCK_ONLY** | `INTERVIEW_AI_CHAIN_ENGINE=openai` + `..._ENABLE_REAL_CALL=True` |
| 꼬리질문 / 적절성 판단 | **MOCK_ONLY** | 위와 동일 |
| 평가/태그 | **REAL** (OpenAI 직접 호출) | `OPENAI_API_KEY` 유효 + 쿼터 |
| 리포트 | 평가 결과 기반 | 평가가 real이면 real |
| 문서 업로드 파싱 | **REAL** (`extract_text_from_document`) | - |
| JD 분석/매칭 | **REAL** (임베딩+Pinecone) | OpenAI + Pinecone 키 |
| STT 적재 | 클라이언트 텍스트 저장 (음성엔진 없음) | 프론트/외부 STT 필요 |
| Worknet 채용검색 | REAL(Open API) | `WORKNET_API_KEY` |

## 5. 테스트 전략

1. **반자동 API 통합 테스트**: DRF `APIClient` / `pytest-django` 로 인증~리포트 흐름을 코드로 검증. JWT 토큰은 테스트 내 발급(비밀번호/실토큰 미저장).
2. **수동 QA 체크리스트**: 실제 구글 OAuth 로그인 등 자동화가 어려운 항목은 브라우저 수동 수행 후 체크리스트 기록.
3. **계정 격리 테스트**: 박소윤/김지윤/홍지윤 3계정의 자원 id 교차 접근 → 404/403 확인.
4. **권한 테스트**: 일반 사용자 토큰으로 `/admin/*` 접근 → 403 확인.

> 프론트(`CAREER_DOT_ZIP_FRONTEND`)는 연결·분석 완료(상세 `real-data-e2e-findings.md` §2). Vite+React, **테스트 프레임워크 없음**(Playwright/Cypress/vitest 미설치) → 화면 QA는 수동 체크리스트. 핵심: 사용자 흐름 대부분이 `SaaSPrototype` 데모(API-first+mock fallback)이며 실제 API 연동 화면은 `/jd`, `/interview`, `/admin/live/*` 로 한정. 백엔드는 `pytest`/`pytest-django`만 존재.

## 6. 환경 / 실행

```bash
# 가상환경 활성화 후
pip install -r requirements.txt
python manage.py migrate

# 서버 실행
python manage.py runserver

# 백엔드 테스트
pytest                      # 전체
pytest apps/interview       # 특정 앱
pytest -k "qa_real"         # 본 QA 추가 테스트(추가 시)
```

실제 AI 호출 QA 시 (별도 `.env.qa.local`, **Git 미커밋**):
```
INTERVIEW_AI_CHAIN_ENGINE=openai
INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=True
```

## 7. 보안 / 개인정보 원칙

- 실제 구글 비밀번호·인증코드·refresh/access token·cookie 값은 코드/로그/README/결과에 **절대 미기록**.
- `.env`, `.env.local`, `.env.qa.local`, `.env.prod` **Git 미커밋** (`.gitignore` 확인 필요).
- 테스트 생성 데이터는 **QA 식별자**(`[QA]`, `qa-`, 타임스탬프) 부착.
- 운영 DB 직접 수정 금지. 현재 `.env` 가 **원격 공유 MySQL** 을 가리키므로 QA 쓰기 시 격리·정리 주의.
- DB 구조 변경 필요 시 임의 수정 금지 → 사유 + migration 필요 여부만 보고.

## 8. 산출물

- `docs/qa/real-data-e2e-qa-plan.md` (본 문서)
- `docs/qa/real-data-e2e-test-cases.md`
- `docs/qa/real-data-e2e-checklist.md`
- `docs/qa/real-data-e2e-result-template.md`
- `docs/qa/real-data-e2e-tracker.xlsx` (추적용)
- (가능 시) `apps/*/tests/test_qa_real_e2e.py` 스캐폴드

## 9. 결과 분류 기준

`PASS` 정상 · `FAIL` 명세 불일치/오류 · `BLOCKED` 인증·키·외부·권한으로 진행 불가 · `NEEDS_CONFIRMATION` 기획/명세 미확정 · `NOT_IMPLEMENTED` 미구현 · `MOCK_ONLY` mock으로만 동작

---

# 📌 v2.0 업데이트 (2026-06-10) — 실제 운영 수준 전환 / access token·사용자 데이터 전면 BLOCKED 반영

> v1.0 대비 변경: 본 QA의 1차 결론을 "기능별 mock 판정"에서 **"인증·사용자 데이터 부재로 로그인 이후 전체 BLOCKED"** 로 격상한다.
> 추가 분석으로 확인된 신규 루트 원인(설정 파일 이원화, 메일 기능 전무, 신규 가입 후 영구 로그인 불가)을 반영한다.

## v2.0-1. 현재 결론 (한 문장)
현재 실제 E2E QA는 **access token 미발급과 사용자 데이터 부재로 인해 로그인 이후 전체 기능이 BLOCKED** 상태이며, 실제 운영 수준 서비스로 가기 위해 **인증·메일·사용자 seed·FE 실연동·관리자 권한·QA DB 분리**가 선행되어야 한다.

## v2.0-2. 신규 확정 루트 원인 (코드 근거)
1. **신규 가입 계정은 영구 로그인 불가**: `accounts/models.py` `is_verified` 기본값 `False` + `LoginSerializer` 가 미인증 시 `403 Email not verified` + **`verify-email` 엔드포인트 자체가 없음**(`accounts/urls.py` 는 signup/login/token-refresh 3개만). → 인증을 풀 방법이 코드에 없어 access token 발급 불가.
2. **메일 기능 전무**: BE 전체에 `send_mail`/`EmailMessage`/`EMAIL_BACKEND` **0건**. 가입 환영 메일·관리자 신규가입 알림·인증 메일·비밀번호 재설정 메일 모두 **NOT_IMPLEMENTED**. `SignupResponseSerializer` 는 "이메일 인증 메일을 확인해주세요" 를 반환하나 **실제 발송 코드 없음**(허위 안내).
3. **설정 파일 이원화 위험**: 실제 활성 설정은 `config/settings.py`(`DJANGO_SETTINGS_MODULE=config.settings`). `config/settings/base.py`(env 강제·CORS 화이트리스트·blacklist 회전) 는 **미사용**. 두 파일이 `SECRET_KEY`, `DEFAULT_PERMISSION_CLASSES`(settings.py=AllowAny / base.py=IsAuthenticated), `EMAIL`, `BLACKLIST_AFTER_ROTATION` 등에서 상충 → 운영 전 **단일화 필요**.
4. **사용자 데이터 부재**: 로컬 `db.sqlite3` 에 user 3건뿐(`user@career.zip`, `testuser@example.com`, `voice@test.com`). 팀원 3계정·관리자 `tripdotzip`·페르소나 4계정 **미존재**. 관리자 권한 계정도 **0건**(전원 `is_staff=0, role=user`). → user_id/profile/jd/session/report 전 단계 부재. (단 `.env` `DATABASE_URL` 이 원격 Aiven 을 가리키므로 운영 DB 실데이터는 별도 확인 필요 = NEEDS_CONFIRMATION.)
5. **FE 인증 미연동·실패 은폐**: `authApi.js`/`userStore.js` 빈 파일, `LoginPage` 는 로그인 API 실패 시 `catch{} → navigate('/profile')` 로 **데모 모드 자동 진입**(실패 은폐). `axiosInstance` 에 `withCredentials` 미설정 → refresh 쿠키 사용 불가, 401 자동 refresh 인터셉터 없음. 로그인 호출 경로 `'/auth/login/'`(끝 슬래시) ↔ BE `path('login')`(슬래시 없음) **불일치 가능**.

## v2.0-3. 전체 BLOCKED 흐름
회원가입(메일 미발송) → is_verified=False & verify-email 부재 → **로그인 403** → access token 없음 → user 인증 불가 → profile/JD/resume/cover_letter/project 생성 불가(전 view `IsAuthenticated`+`request.user` 필터) → session 생성 불가 → question_id 없음 → answer_id 없음 → followup/STT/evaluation/report 생성 불가 → mypage/admin 에서 확인할 데이터 없음.

## v2.0-4. 회원가입 메일 요구사항 (신규)
| 메일 | 트리거 | 수신자 | 민감정보 | 발송 실패 정책(MVP 추천) | 상태 |
|---|---|---|---|---|---|
| 가입 환영 | signup 201 | 가입 사용자 | 포함 금지 | 가입은 성공 처리, 메일 실패는 로그+관리자 알림 | NOT_IMPLEMENTED |
| 관리자 신규가입 알림 | signup 201 | `ADMIN_NOTIFICATION_EMAIL`(env, 예 tripdotzip@gmail.com) | 비번/토큰/쿠키 **절대 미포함** | 동기 발송, 실패 시 로그 | NOT_IMPLEMENTED |
| 이메일 인증 | signup 201 | 가입 사용자 | 인증 토큰만(URL) | 미발송 시 verify 불가 | NOT_IMPLEMENTED |
| 비밀번호 재설정 | reset 요청 | 사용자 | 1회용 토큰 | - | NOT_IMPLEMENTED |

필요 env(.env 미커밋): `EMAIL_BACKEND, EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS, DEFAULT_FROM_EMAIL, ADMIN_NOTIFICATION_EMAIL`. MVP=동기 발송, 운영=Celery/Redis 비동기 추천. local/QA/prod 환경별 분리.

## v2.0-5. 최소 복구안 (1/2/3안) 및 MVP 추천
- **1안 — QA seed**: 팀원3+페르소나4+관리자 계정을 `data migration` 또는 `loaddata` fixture 로 생성, `is_verified=True`, 관리자 `is_staff=True/role=admin`, 기본 profile/JD/resume/session seed. 비밀번호는 env/수동, 문서 미기록. 장점: 즉시 E2E 가능, OAuth/메일 의존 없음. 단점: 실제 가입 흐름 미검증, 메일 미검증. 소요: 0.5~1일. 위험: 낮음(운영 DB 분리 전제).
- **2안 — verify-email + 메일 최소 구현**: `GET /auth/verify-email` + 가입 시 환영/관리자/인증 메일 동기 발송(SMTP). 실제 가입→인증→로그인→토큰 흐름 검증. OAuth 후순위. 장점: 운영 흐름 실검증. 단점: SMTP 셋업·앱 비밀번호 필요, 메일 도달성 변수. 소요: 1.5~2.5일. 위험: 중(메일 설정).
- **3안 — 이메일 로그인 기준 E2E(발표/운영 대비)**: OAuth 제외, 이메일/비번 로그인만 운영 수준으로 연결(가입~환영메일~관리자알림~인증~로그인~프로필~JD~면접~평가~리포트~마이페이지). 질문/꼬리질문 mock 명시. 관리자 권한 seed/화면 부여. 운영서 SMTP·QA DB·audit 연결. 장점: 데모·운영 동시 충족. 단점: OAuth 미포함. 소요: 3~5일. 위험: 중.
- **MVP 추천**: **1안으로 즉시 E2E 차단 해제 → 동시에 2안(verify-email+환영/관리자 메일)을 운영 경로로 구현**. 이유: 1안은 토큰/데이터 블로커를 당일 해소해 김지윤/홍지윤/박은지/김이선 담당 기능 QA를 즉시 시작하게 하고, 2안은 "실제 영리 서비스 운영" 요건(실가입·메일)을 충족. OAuth(구글/임시 페르소나 계정)는 실계정 미확인 → **BLOCKED 유지/후순위**.

---

# ✅ v2.1 P0 인증/토큰/메일 복구 — 구현 완료 (feature/auth-token-email-recovery)

> 1안(seed) + 2안(verify-email+메일)을 함께 구현. access token 블로커 해소 → 실제 E2E QA 시작 가능.
> DB 구조 변경 없음(서명 토큰 사용) — migration 불필요, ERD 영향 없음. `makemigrations accounts --check` = "No changes detected".

## 신규/변경 API
| 메서드 | 경로 | 설명 | 권한 |
|---|---|---|---|
| GET | /api/v1/auth/verify-email?token= | 이메일 인증(서명 토큰, 기본 24h). 성공 200 / 만료·위조 400 | AllowAny |
| POST | /api/v1/auth/logout | refresh cookie 삭제. 200 | IsAuthenticated |
| POST | /api/v1/auth/signup | (변경) 성공 시 환영+관리자 알림 메일 발송(실패해도 가입 성공) | AllowAny |
| POST | /api/v1/auth/login | (유지) verified 계정 access_token + refresh cookie | AllowAny |
| POST | /api/v1/auth/token/refresh | (유지) cookie 기반 재발급 | AllowAny |

## 메일
- 환영 메일(HTML+text, 인증 링크 `${FRONTEND_BASE_URL}/verify-email?token=`), 관리자 신규가입 알림(민감정보 미포함).
- 설정: console backend 기본(로컬), `.env` SMTP 전환. env: EMAIL_*, DEFAULT_FROM_EMAIL, ADMIN_NOTIFICATION_EMAIL, FRONTEND_BASE_URL, EMAIL_VERIFICATION_TOKEN_MAX_AGE.

## QA seed
- `python manage.py seed_qa_users` — 팀원3+페르소나4+관리자(tripdotzip, role=admin/is_staff) 생성, 전원 is_verified=True. 비밀번호는 `QA_SEED_PASSWORD` env 또는 대화형 입력(문서 미기록).

## FE 실연동
- `/auth/login`, `/auth/signup`, `/verify-email` 실 API 연동. 로그인 실패 데모 자동진입 제거. axios `withCredentials`+401 refresh 인터셉터. Google 버튼 비활성("준비 중").

## 검증 결과 (sandbox)
- `manage.py check` 0 issues / `makemigrations accounts --check` 변경 없음 / `python manage.py test apps.accounts` **16 passed**.
- FE `vite build` **✓ 1897 modules transformed, built OK**(기존 dist 디렉터리 unlink 권한 이슈는 환경 아티팩트).

## 상태 변화
- verify-email / logout / 환영·관리자 메일: NOT_IMPLEMENTED → **PASS(구현+테스트 통과)**.
- 로그인 후 access token: BLOCKED → **PASS**(seed 또는 verify 후). 후속 기능(프로필~리포트~관리자)은 토큰 확보로 **BLOCKED 해소, 실행 검증 단계로 이동**.
- Google OAuth: **NOT_IMPLEMENTED 유지(후순위)**. 질문/꼬리질문: **MOCK_ONLY 유지**.
