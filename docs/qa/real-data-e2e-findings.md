# Career.zip 실제 데이터 기반 통합 E2E QA — Findings (발견 사항)

> v1.0 · 2026-06-10 · 분석 대상: `CAREER_DOT_ZIP`(main, submodule) / `CAREER_DOT_ZIP_BACKEND`(develop) / `CAREER_DOT_ZIP_FRONTEND`
> ⚠️ 실제 비밀번호/토큰/쿠키/인증코드 미기록. `.env*` 커밋 금지.

## 0. 레포 구성

| 레포 | 형태 | 비고 |
|---|---|---|
| `CAREER_DOT_ZIP` | main, **git submodule** 래퍼 | `.gitmodules` 로 BE/FE 2개 서브모듈 참조 |
| `CAREER_DOT_ZIP_BACKEND` | Django + DRF + SimpleJWT | 현재 브랜치 `develop` |
| `CAREER_DOT_ZIP_FRONTEND` | Vite + React18 + react-router7 + zustand + react-query + axios | 테스트 프레임워크 없음 |

- 브랜치: BE `develop` (origin/develop 추적). `feature/qa-real-data-e2e` 아직 없음.
- **CRLF/LF**: BE develop 워킹트리에 293개 M 표시 → `git diff -w` 0건, 35368 insert == 35368 delete → **순수 개행 차이, 실제 코드 변경 아님. 건드리지 않음.**
- **`.git/index.lock` 점유 중** (IDE git 프로세스 추정) → `git add/commit/push` **BLOCKED**. 브랜치/커밋은 사용자가 직접 수행.

## 1. Backend — 명세 vs 실제 구현 대조

라우팅: `config/urls.py`. **면접 세션 API가 이중 표면**으로 존재 →
- 중첩형: `apps.interview.urls` → `/api/v1/interviews/sessions/...`
- 평면 MVP: `apps.interview.mvp_urls` → `/api/v1/sessions`, `/answers`, `/answers/{id}/stt`, `/answers/{id}/followup`
- **프론트 `interviewApi.js` 는 평면 MVP 표면을 호출** → QA·정식 기준 = MVP 평면형. 중첩형 정리 여부 확인 필요.

| 명세 엔드포인트 | 실제 구현 | 상태 |
|---|---|---|
| POST /auth/signup | ✅ `SignupView` (중복 409) | PASS(실행필요) |
| GET /auth/verify-email | ❌ 라우트/뷰 없음 | **NOT_IMPLEMENTED** |
| POST /auth/login | ✅ `LoginView` (access body + refresh cookie) | PASS(실행필요) |
| POST /auth/token/refresh | ✅ `CookieTokenRefreshView` | PASS(실행필요) |
| POST /auth/logout | ❌ 라우트/뷰 없음 | **NOT_IMPLEMENTED** |
| Google OAuth | ❌ 백엔드 라우트 없음 (FE는 mock 토스트) | **NOT_IMPLEMENTED** |
| POST/GET/PATCH /users/me/profile | ✅ `UserProfileView` | PASS(실행필요) |
| POST /jds, GET /jds, GET/DELETE /jds/{id} | ✅ `JDListCreateView`/`JDDetailView` | PASS(실행필요) |
| POST /jds/upload | ❌ → 실제 `POST /documents/upload` 일원화 | **NEEDS_CONFIRMATION** |
| POST /jds/{id}/analyze | ❌ → 실제 `POST /analysis/analyze/` | **NEEDS_CONFIRMATION** |
| POST /jds/{id}/match | ❌ → 실제 `POST /analysis/match/` (명세 미확정) | **NEEDS_CONFIRMATION** |
| POST /resumes (+education/careers/skills/certificates), GET /resumes/{id} | ✅ | PASS(실행필요) |
| POST /resumes/upload | ❌ → `POST /documents/upload` | **NEEDS_CONFIRMATION** |
| POST/GET /cover-letters, GET /cover-letters/{id} | ✅ | PASS(실행필요) |
| POST/GET /projects, PATCH /projects/{id} | ✅ | PASS(실행필요) |
| POST /sessions, GET /sessions/{id}, PATCH status | ✅ (MVP) | PASS(실행필요) |
| GET /sessions/{id}/questions, POST .../generate | ✅ (MVP) | PASS / **MOCK_ONLY**(생성 엔진) |
| POST /answers | ✅ (MVP) | PASS(실행필요) |
| PATCH or POST /answers/{id}/stt | ✅ **둘 다** 구현 (`MVPSTTResultUpdateView` patch+post) | PASS(실행필요) |
| POST /answers/{id}/followup | ✅ (GENERATE_FOLLOWUP / NEXT_QUESTION 분기) | PASS / MOCK_ONLY |
| GET /evaluations/{answer_id} (+strength/weakness tags) | ✅ | PASS(실행필요, real OpenAI) |
| GET /sessions/{id}/report | ✅ `SessionFinalReportView` | PASS(실행필요) |
| GET /mypage/interviews | ✅ `InterviewHistoryView` | PASS(실행필요) |
| GET /admin/personas, PATCH .../active-template | ✅ (`apps.prompt`) | PASS(실행필요) |
| POST/DELETE /admin/prompt-templates, versions, default-version | ✅ | PASS(실행필요) |
| GET /admin/members, PATCH .../status, GET /admin/audit-logs | ✅ (`apps.admin_api`) | PASS(실행필요) |

권한/격리:
- 기본 인증 JWT, 기본 권한 `IsAuthenticated`.
- 관리자: `IsAdminUserOrRole` = `is_staff or role=='admin'` → 일반 토큰 admin 접근 시 **403** 기대.
- 사용자 자원 격리: `get_object_or_404(..., session__user=request.user)` → 타 사용자 접근 시 **404** (명세가 403 요구 시 불일치).

## 2. Frontend — 화면/라우트/API 연결 상태

핵심: `App.jsx` 의 거의 모든 사용자 라우트가 단일 `SaaSPrototype.jsx`(1351줄, Figma 기반 통합 데모)로 매핑. 데모는 **"API 우선 호출 → 실패 시 mock fallback"** 패턴 + 다수 `source:'mock'` 데이터.

| 화면 | 라우트 | 실제 API 연결 | 상태 |
|---|---|---|---|
| 회원가입 | `/signup` | ❌ 프로토타입(`authApi.js` 0바이트, mock 토큰 생성) | MOCK_ONLY |
| 로그인 | `/login` | ❌ 프로토타입/mock fallback | MOCK_ONLY |
| 구글/카카오/네이버 로그인 | 버튼 | ❌ `"Google 로그인은 mock입니다"` 토스트만 | **NOT_IMPLEMENTED** |
| 프로필/온보딩 | `/onboarding`,`/mypage/profile` | ❌ 프로토타입 | MOCK_ONLY |
| JD 입력 | `/data/jd` (proto) / **`/jd`** (live) | `/jd` = `JdInputPage`+`jdApi.createJd` ✅ | `/jd` PASS / proto MOCK |
| JD 업로드 | `/data/jd` | ❌ FE 업로드 클라이언트 없음 | NOT_IMPLEMENTED(FE) |
| 이력서 입력/업로드 | `/data/resume` | ❌ 프로토타입 | MOCK_ONLY |
| 자소서 입력 | `/data/cover-letter` | ❌ 프로토타입 | MOCK_ONLY |
| 프로젝트 입력 | `/data/projects` | ❌ 프로토타입 | MOCK_ONLY |
| 면접 설정/세션/질문/답변/STT/꼬리질문 | `/interview/*` (proto) / **`/interview`** (live) | `/interview` = `VoiceInterviewPage` + `useInterview`(interviewApi 전체) + `useSTT`/`useTTS` ✅ | `/interview` PASS(실행필요) / proto MOCK |
| 평가 결과 | `/interview/result` | ❌ `pages/evaluation` 0 파일, 프로토타입 | MOCK_ONLY |
| 최종 리포트 | `/report/*` | ❌ 프로토타입 (단, `interviewApi.getSessionReport` 는 live 흐름서 호출) | MOCK_ONLY(화면) |
| 마이페이지 면접기록 | `/mypage/interviews` | ❌ 프로토타입 | MOCK_ONLY |
| 관리자 로그인/회원/프롬프트 | **`/admin/live/*`** | `adminApi.js` 전체 연결 ✅ (login/members/status/personas/templates/versions) | PASS(실행필요) |
| 관리자 audit log | `/admin/audit-logs` | ❌ `adminApi` 에 audit-logs 호출 없음, 프로토타입 | NOT_IMPLEMENTED(FE) |

기타 FE:
- 토큰: `localStorage('access_token')` + axios 요청 인터셉터 Bearer. **401 자동 refresh 인터셉터 없음** → refresh cookie 흐름 FE 미연동.
- STT/TTS: 브라우저 Web Speech API(`webkitSpeechRecognition`, `speechSynthesis`) — **클라이언트측**. 백엔드 STT 엔드포인트는 결과 텍스트 저장만.
- 테스트 프레임워크: 없음 (Playwright/Cypress/vitest/jest 미설치) → E2E는 **수동 체크리스트**.
- `dist/` 존재 → `vite build` 수행 이력 있음. `.env.example` 0바이트(템플릿 비어있음).

## 3. mock 잔존 지점

| 위치 | 파일 | mock 내용 | 실제 전환 가능 | 영향 | 조치 |
|---|---|---|---|---|---|
| BE AI 엔진 | `apps/interview/services/ai_chain_engine_factory.py`, `ai_chain_mock_engine.py` | 질문/꼬리질문/적절성 deterministic mock | env `INTERVIEW_AI_CHAIN_ENGINE=openai` + `..._ENABLE_REAL_CALL=True` | 질문/꼬리질문 실데이터 아님 | real 전환 후 재검증 |
| BE OpenAI 엔진 | `ai_chain_openai_engine.py` | 실패/파싱오류 시 mock fallback | - | real 실패 시 조용히 mock | 로그/모니터링 |
| BE analysis | `apps/analysis/services/project_service.py` | `extract_projects`/`merge_with_github`/`score_projects` NotImplementedError | 구현 필요 | 매칭 정확도 한계 | 구현/명세 확인 |
| FE 전체 사용자 흐름 | `pages/prototype/SaaSPrototype.jsx` | mock JD/토큰/오디트, API-first+mock fallback | 백엔드 연동 시 부분 real | 화면 QA = 데모 | live 화면으로 교체 필요 |
| FE 인증 | `api/authApi.js`(빈파일), `store/userStore.js`(빈파일) | 미구현 | 구현 필요 | 로그인 실데이터 아님 | auth 클라이언트 구현 |
| FE 소셜 로그인 | SaaSPrototype 버튼 | Google/Kakao/Naver mock 토스트 | OAuth 구현 필요 | OAuth QA 불가 | BE+FE 구현 |

실데이터 동작 영역(참고): BE 문서 파싱(`extract_text_from_document`), JD 분석 임베딩+Pinecone, **평가(OpenAI 직접 호출)**, Worknet Open API.

## 4. 보안 / 개인정보 위험

| 항목 | 위험도 | 내용 | 조치 |
|---|---|---|---|
| 원격 공유 MySQL | 중 | BE `.env` `DATABASE_URL`=Aiven Cloud MySQL(`defaultdb`). 로컬 QA 쓰기가 공유 DB 반영 | QA 식별자(`[QA]`)·정리, 별도 QA DB 검토 |
| refresh cookie `secure=False` | 중 | `LoginView` 개발용 설정 | prod 전 `secure=True` |
| FE 토큰 localStorage 저장 | 중 | XSS 시 access_token 노출 | httpOnly 쿠키 전략 검토 |
| Google OAuth mock | 정보 | 실제 인증 없음 | OAuth는 수동 QA / 구현 후 검증 |
| `.env` 커밋 여부 | 확인 | `.gitignore` 점검 필요 | `git status`에 .env 미노출 확인 |
| 임시 QA 구글계정 실재 여부 | BLOCKED 가능 | `careerzip.qa.*@gmail.com` 실제 접근 가능 계정인지 미확인 | 팀이 직접 생성/접근. 미존재 시 OAuth BLOCKED, 이메일가입 대체 |

## 5. 수정 필요 우선순위

| 순위 | 항목 | 분류 | 사유 |
|---|---|---|---|
| P0 | verify-email 또는 가입 후 verified 처리 경로 | NOT_IMPLEMENTED | is_verified=False 기본 → 로그인 불가 블로커 |
| P0 | 면접 세션 API 표면(중첩 vs MVP) 확정 | NEEDS_CONFIRMATION | E2E·FE 기준 결정 |
| P0 | FE 인증/온보딩 실연동 (authApi/userStore 구현) | MOCK_ONLY | 사용자 흐름 화면 QA 불가 |
| P1 | Google OAuth BE+FE 구현 또는 범위 제외 결정 | NOT_IMPLEMENTED | 시나리오 전제(구글 로그인) |
| P1 | JD/이력서 upload·analyze·match 경로 명세 정합 | NEEDS_CONFIRMATION | FE 연동·명세 일치 |
| P1 | 운영/공유 DB와 QA DB 분리 | 보안 | QA 데이터 오염 방지 |
| P2 | refresh cookie secure / FE 401 refresh 인터셉터 | 보안/기능 | 토큰 수명 흐름 |
| P2 | analysis project_service 구현 | NOT_IMPLEMENTED | 매칭 정확도 |
| P2 | 관리자 audit-logs FE 연동 | NOT_IMPLEMENTED(FE) | 관리자 감사 화면 |

## 6. 임시 페르소나 계정 주의

`careerzip.qa.kimhamzzi/hongizzi/parkjwi/parkilzzi@gmail.com` 4계정은 **실제 구글 계정 존재 여부 미확인**. Google OAuth 자체가 미구현이므로:
- OAuth 로그인 검증 = **BLOCKED** (구현+실계정 필요).
- 대체: 이메일/비밀번호 회원가입(`POST /auth/signup`) + 관리자/DB로 `is_verified=True` 처리 후 로그인. 이 경로로 페르소나 시나리오(프로필~리포트) 진행 가능.

---

# 📌 v2.0 추가 발견 (2026-06-10)

## 7. 신규 루트 원인 — 인증/메일/설정 (코드 근거)

### 7.1 설정 파일 이원화 (신규)
`DJANGO_SETTINGS_MODULE=config.settings` (manage.py/wsgi/asgi 일치) → **활성 설정 = `config/settings.py`**.
별도 `config/settings/base.py` 는 존재하나 **미사용**. 두 파일 상충 지점:
| 항목 | config/settings.py (활성) | config/settings/base.py (미사용) |
|---|---|---|
| SECRET_KEY | 하드코딩 `django-insecure-...` | env 강제 |
| DEFAULT_PERMISSION_CLASSES | **AllowAny** | IsAuthenticated |
| 필수 env 체크 | 없음 | SECRET_KEY/DATABASE_URL/REDIS_URL/OPENAI 강제 |
| BLACKLIST_AFTER_ROTATION | False | True (token_blacklist 앱 미설치 → 활성화 시 에러 위험) |
| EMAIL_* | 없음 | 없음 |
| CORS | ALLOW_ALL | 화이트리스트 블록(주석) |
→ 운영 전 **단일 설정 + 환경분기(env)** 로 통합 필요. 현재 전역 권한이 AllowAny 라 view 별 `IsAuthenticated` 미지정 엔드포인트는 무인증 노출 위험(점검 필요).

### 7.2 메일 기능 전무 (신규 / 운영 필수)
- `grep send_mail|EmailMessage|EMAIL_BACKEND` → BE **0건**. `settings.py`/`.env` 에 EMAIL 설정 **0건**.
- `SignupView` 는 user 생성 후 **어떤 메일도 발송하지 않음**. 응답 메시지만 "이메일 인증 메일을 확인해주세요" (실제 미발송 → 사용자 오인 유발).
- 결론: 가입 환영 / 관리자 신규가입 알림 / 이메일 인증 / 비밀번호 재설정 메일 **전부 NOT_IMPLEMENTED**.

### 7.3 신규 가입 → 영구 로그인 불가 체인 (재확인·격상)
`is_verified=False`(기본) + `LoginSerializer` 403 차단 + `verify-email` 라우트 부재 → **신규 계정은 코드상 인증 해제 경로가 없음** → access token 영구 미발급. 기존 로그인 가능 계정은 DB에서 수동 `is_verified=True` 처리된 3건뿐.

### 7.4 DB 사용자 실태 (로컬 sqlite 기준)
accounts_user 3건: `user@career.zip`(verified), `testuser@example.com`(verified), `voice@test.com`(**unverified→로그인불가**). **관리자/팀원/페르소나 계정 전무, is_staff/role=admin 계정 0건.** (원격 Aiven DB 실데이터는 미접근 → NEEDS_CONFIRMATION.)

### 7.5 FE 인증 실패 은폐 (신규)
`LoginPage.handleSubmit` 의 `catch { navigate('/profile') }` → 로그인 API 실패해도 데모 화면 진입 → **access token 블로커가 화면상 드러나지 않음**. `axiosInstance` 에 `withCredentials` 미설정(refresh 쿠키 불가) + 401 refresh 인터셉터 없음. 로그인 URL `'/auth/login/'`(slash) ↔ BE `login`(no slash) 불일치 가능 → 점검 필요.

## 8. 기능별 연쇄 BLOCKED (선행 데이터/토큰 기준)
| 기능 | 선행 데이터/토큰 | 상태 | 막히는 이유 | 대체 QA |
|---|---|---|---|---|
| 회원가입 | - | PASS(실행필요) | - | - |
| 가입 환영 메일 | EMAIL 설정 | NOT_IMPLEMENTED | 발송 코드/설정 없음 | - |
| 관리자 신규가입 알림 | ADMIN_NOTIFICATION_EMAIL | NOT_IMPLEMENTED | 미구현 | - |
| 이메일 인증 | verify-email | NOT_IMPLEMENTED | 라우트 부재 | seed로 verified 처리 |
| 로그인 | is_verified=True | BLOCKED | 신규계정 인증 불가 | seed 계정 |
| Google OAuth | OAuth 라우트 | NOT_IMPLEMENTED | BE/FE 모두 mock/미구현 | 이메일 로그인 |
| access token | 로그인 성공 | BLOCKED | 로그인 막힘 | seed 후 발급 |
| refresh token | 로그인+withCredentials | BLOCKED(FE) | FE 쿠키 미사용 | - |
| 프로필 등록 | access token | BLOCKED | IsAuthenticated | seed 후 |
| JD 등록 | access token | BLOCKED | 〃 | seed 후 |
| JD 분석/매칭 | jd_id+OpenAI/Pinecone | BLOCKED | 토큰·jd_id 부재 / 경로 명세 불일치(NC) | - |
| 이력서/자소서/프로젝트 | access token | BLOCKED | 〃 | seed 후 |
| 문서 업로드 | access token | BLOCKED→REAL | 토큰 부재(엔진은 real) | - |
| 세션 생성 | access token+profile | BLOCKED | 〃 | seed 후 |
| 질문 생성 | session_id | BLOCKED→MOCK_ONLY | 토큰/세션 부재(엔진 mock) | env real 전환 |
| 답변 제출 | question_id | BLOCKED | 토큰/질문 부재 | - |
| STT/음성 | answer | BLOCKED | 백엔드는 텍스트 적재만(음성엔진X) | FE Web Speech |
| TTS | 질문 | MOCK_ONLY(FE) | 브라우저 speechSynthesis | - |
| 꼬리질문 | answer_id | BLOCKED→MOCK_ONLY | 토큰/answer 부재 | env real |
| 평가/태그 | answer_id+OpenAI키 | BLOCKED→REAL | 토큰·answer 부재 | 키/쿼터 |
| 최종 리포트 | 평가 완료 | BLOCKED | 선행 전부 막힘 | - |
| 마이페이지 | session/report | BLOCKED | 데이터 없음 | seed 후 |
| 관리자 회원목록 | admin 토큰 | BLOCKED | admin 계정/권한 없음 | admin seed |
| 프롬프트/페르소나 관리 | admin 토큰 | BLOCKED | 〃 | admin seed |
| audit log | admin 토큰 | BLOCKED | 〃 | admin seed |
| 회원 탈퇴/개인정보 삭제 | - | NOT_IMPLEMENTED | 라우트 부재(확인 필요) | - |
| QA DB 분리 | - | NEEDS_CONFIRMATION | 현재 원격 공유 DB | 별도 DB/스키마 |
| AWS 배포 | - | NEEDS_CONFIRMATION | 문서 외부 | - |
| GitHub Actions | .github/workflows | NEEDS_CONFIRMATION | ci/deploy 존재, 검증 필요 | - |
| Swagger | drf-spectacular/yasg | NOT_IMPLEMENTED | 패키지/설정 미존재 | - |
