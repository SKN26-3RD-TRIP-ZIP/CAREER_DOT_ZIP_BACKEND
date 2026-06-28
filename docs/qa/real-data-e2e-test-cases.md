# Career.zip 실제 데이터 기반 통합 E2E 테스트 케이스

> v1.0 · 2026-06-10 · 기준 브랜치 `develop` · API Base `/api/v1`
> 상태 표기: PASS / FAIL / BLOCKED / NEEDS_CONFIRMATION(NC) / NOT_IMPLEMENTED(NI) / MOCK_ONLY(MOCK)
> "실제 결과"는 실행 전 `(미실행)`. "상태"는 코드 분석으로 사전 판정 가능한 경우 표기, 실행 확인 필요 시 `(실행필요)`.
> ⚠️ 실제 계정 비밀번호/토큰/쿠키 값은 본 표에 기입 금지.

## 공통 / 인증 (계정 무관)

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| AUTH-01 | parksoyun9084 | 박소윤 | 인증 | 회원가입 성공 | `POST /auth/signup` | `{email, name:"[QA]박소윤", password}` | 201, user_id 반환, "이메일 인증" 안내 메시지 | (미실행) | (실행필요) | - |
| AUTH-02 | parksoyun9084 | 박소윤 | 인증 | 중복 회원가입 | 동일 email 재가입 | 기가입 email | 409 Conflict | (미실행) | (실행필요) | - |
| AUTH-03 | parksoyun9084 | 박소윤 | 인증 | 미인증 로그인 차단 | `is_verified=False` 상태 로그인 | email/password | 403 "Email not verified" | (미실행) | (실행필요) | verify-email 엔드포인트 없음(아래) |
| AUTH-04 | - | - | 인증 | 이메일 인증 | `GET /auth/verify-email` | 토큰 | 인증 완료 → is_verified=True | (미실행) | **NI** | 라우트·뷰 미존재. 가입 후 로그인 불가 블로커 |
| AUTH-05 | parksoyun9084 | 박소윤 | 인증 | 로그인 성공 | `POST /auth/login` (수동 verified 후) | email/password | 200, access_token + refresh cookie | (미실행) | (실행필요) | is_verified 수동 set 선행 필요 |
| AUTH-06 | parksoyun9084 | 박소윤 | 인증 | 구글 로그인 | OAuth 로그인 | 구글 계정 | 성공 → 토큰 발급 | (미실행) | **NI** | 백엔드에 google/oauth 라우트·뷰 없음. 프론트/별도 처리 여부 확인 |
| AUTH-07 | parksoyun9084 | 박소윤 | 인증 | access token 발급/저장/갱신 | `POST /auth/token/refresh` | refresh cookie | 200, 새 access_token | (미실행) | (실행필요) | - |
| AUTH-08 | parksoyun9084 | 박소윤 | 인증 | refresh 쿠키 동작 | 쿠키 없이 refresh | (no cookie) | 401 | (미실행) | (실행필요) | - |
| AUTH-09 | parksoyun9084 | 박소윤 | 인증 | 로그아웃 | `POST /auth/logout` | access token | 로그아웃 처리 | (미실행) | **NI** | 라우트·뷰 미존재 |
| AUTH-10 | parksoyun9084 | 박소윤 | 인증 | 로그아웃 후 보호 API 차단 | 무효 토큰으로 보호 API | 만료/무효 token | 401 | (미실행) | (실행필요) | 서버 로그아웃 없음 → 클라 토큰 폐기 전제 확인 |
| SEC-01 | parksoyun9084 | 박소윤 | 보안 | 사용자 데이터 격리 | 타 사용자 `jd_id`/`resume_id`/`session_id` 조회 | 김지윤 자원 id | 404 (get_object_or_404 + user 필터) | (미실행) | (실행필요) | 명세상 403 기대면 불일치 → 확인 |
| SEC-02 | jykim4169 | 김지윤 | 보안 | admin API 권한 차단 | 일반 토큰으로 `GET /admin/members` | user role token | 403 | (미실행) | (실행필요) | IsAdminUserOrRole 적용됨 |

---

## 1) 박소윤 — 신입/전공, 백엔드, text 모드, practical 페르소나 (핀테크 백엔드)

JD 키워드: Django, DRF, MySQL, JWT, Docker, AWS EC2, GitHub Actions

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| SY-01 | parksoyun9084 | 박소윤 | 프로필 | 프로필 등록 | `POST /users/me/profile` | 신입/전공, 백엔드 희망 | 201/200 | (미실행) | (실행필요) | - |
| SY-02 | parksoyun9084 | 박소윤 | 프로필 | 프로필 조회 | `GET /users/me/profile` | - | 200, 등록값 일치 | (미실행) | (실행필요) | - |
| SY-03 | parksoyun9084 | 박소윤 | 프로필 | 프로필 수정 | `PATCH /users/me/profile` | 일부 필드 변경 | 200, 반영 | (미실행) | (실행필요) | - |
| SY-04 | parksoyun9084 | 박소윤 | JD | JD 직접 입력 등록 | `POST /jds` | 핀테크 백엔드 JD 텍스트 | 201, jd_id | (미실행) | (실행필요) | 사용자 직접 입력(합법) |
| SY-05 | parksoyun9084 | 박소윤 | JD | JD 파일 업로드 | `POST /jds/upload` | JD 파일 | 업로드/파싱 | (미실행) | **NC** | input/urls에 `/jds/upload` 없음. 실제는 `POST /documents/upload`. 경로 불일치 |
| SY-06 | parksoyun9084 | 박소윤 | JD | JD 분석 | `POST /jds/{jd_id}/analyze` | jd_id | PROCESSING→COMPLETED | (미실행) | **NC** | 해당 경로 없음. 실제는 `POST /api/v1/analysis/analyze/`. 명세 경로 확인 |
| SY-07 | parksoyun9084 | 박소윤 | JD | JD 매칭 | `POST /jds/{jd_id}/match` | jd_id | 매칭 결과 | (미실행) | **NC** | 명세상 "미확정". 실제는 `/analysis/match/` 존재 |
| SY-08 | parksoyun9084 | 박소윤 | 이력서 | 이력서 등록 | `POST /resumes` | 서버·DB·인프라 경험 | 201, resume_id | (미실행) | (실행필요) | - |
| SY-09 | parksoyun9084 | 박소윤 | 이력서 | 학력/경력/스킬/자격 | `POST /resumes/{id}/education|careers|skills|certificates` | 각 항목 | 201 | (미실행) | (실행필요) | - |
| SY-10 | parksoyun9084 | 박소윤 | 이력서 | 이력서 업로드 | `POST /resumes/upload` | 이력서 파일 | 업로드/파싱 | (미실행) | **NC** | input/urls에 `/resumes/upload` 없음. `/documents/upload` 사용 |
| SY-11 | parksoyun9084 | 박소윤 | 이력서 | 이력서 조회 | `GET /resumes/{resume_id}` | resume_id | 200 | (미실행) | (실행필요) | - |
| SY-12 | parksoyun9084 | 박소윤 | 자소서 | 자소서 등록 | `POST /cover-letters` | 안정적 API 설계 강조 | 201 | (미실행) | (실행필요) | - |
| SY-13 | parksoyun9084 | 박소윤 | 자소서 | 자소서 목록/상세 | `GET /cover-letters`, `/{id}` | - | 200 | (미실행) | (실행필요) | - |
| SY-14 | parksoyun9084 | 박소윤 | 프로젝트 | 프로젝트 등록 | `POST /projects` | Career.zip 인증/입력/배포 담당 | 201 | (미실행) | (실행필요) | - |
| SY-15 | parksoyun9084 | 박소윤 | 프로젝트 | 프로젝트 수정/목록 | `PATCH /projects/{id}`, `GET /projects` | - | 200 | (미실행) | (실행필요) | - |
| SY-16 | parksoyun9084 | 박소윤 | 세션 | 면접 세션 생성 | `POST /sessions` (MVP) | mode=text, persona=practical | 201, session_id | (미실행) | (실행필요) | MVP 평면 API |
| SY-17 | parksoyun9084 | 박소윤 | 세션 | 세션 조회/상태 | `GET /sessions/{id}`, `PATCH /sessions/{id}/status` | - | 200 | (미실행) | (실행필요) | - |
| SY-18 | parksoyun9084 | 박소윤 | 질문 | 질문 생성 | `POST /sessions/{id}/questions/generate` | JD+이력서 기반 | 질문 생성 | (미실행) | **MOCK** | 기본 mock 엔진. real은 env 전환 필요 |
| SY-19 | parksoyun9084 | 박소윤 | 질문 | 질문 목록 | `GET /sessions/{id}/questions` | - | 200, 질문 리스트 | (미실행) | (실행필요) | - |
| SY-20 | parksoyun9084 | 박소윤 | 답변 | 답변 제출(text) | `POST /answers` | 텍스트 답변 | 201, answer_id | (미실행) | (실행필요) | - |
| SY-21 | parksoyun9084 | 박소윤 | 꼬리질문 | 꼬리질문/NEXT 분기 | `POST /answers/{id}/followup` | answer_id | GENERATE_FOLLOWUP 또는 NEXT_QUESTION | (미실행) | **MOCK** | 분기 구현됨, 생성 로직 mock |
| SY-22 | parksoyun9084 | 박소윤 | 평가 | 평가 조회 | `GET /evaluations/{answer_id}` | answer_id | 200, 평가 | (미실행) | (실행필요) | OpenAI 직접 호출(real). 키/쿼터 BLOCKED 가능 |
| SY-23 | parksoyun9084 | 박소윤 | 평가 | 강점/약점 태그 | `GET /evaluations/{id}/strength-tags|weakness-tags` | answer_id | 200, 태그 | (미실행) | (실행필요) | - |
| SY-24 | parksoyun9084 | 박소윤 | 리포트 | 최종 리포트 | `GET /sessions/{id}/report` | session_id | 200, 리포트 | (미실행) | (실행필요) | - |
| SY-25 | parksoyun9084 | 박소윤 | 마이페이지 | 면접 기록 확인 | `GET /api/v1/mypage/interviews` | - | 200, 세션 기록 | (미실행) | (실행필요) | - |

---

## 2) 김지윤 — 신입/전공, AI 서비스, voice 모드, coach 페르소나 (LLM 질문생성)

JD 키워드: Python, GPT API, Prompt Engineering, RAG, Vector DB, 질문 생성, 꼬리질문

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| JY-01 | jykim4169 | 김지윤 | 인증 | 구글 로그인 | OAuth | 구글 계정 | 성공 | (미실행) | **NI** | 백엔드 OAuth 미구현 → 수동/프론트 확인 |
| JY-02 | jykim4169 | 김지윤 | 프로필 | 프로필 조회/수정 | `GET`/`PATCH /users/me/profile` | AI 서비스 개발자 | 200 | (미실행) | (실행필요) | - |
| JY-03 | jykim4169 | 김지윤 | JD | JD 등록 | `POST /jds` | LLM 질문생성 JD 텍스트 | 201 | (미실행) | (실행필요) | 박소윤과 다른 JD(비중복) |
| JY-04 | jykim4169 | 김지윤 | 질문 | 질문 생성 정확도 | `POST /sessions/{id}/questions/generate` | JD 키워드 반영 여부 | JD 키워드 기반 질문 | (미실행) | **MOCK** | real 전환 시에만 정확도 평가 의미. mock은 deterministic |
| JY-05 | jykim4169 | 김지윤 | 세션 | voice 세션 생성 | `POST /sessions` | mode=voice, persona=coach | 201 | (미실행) | (실행필요) | - |
| JY-06 | jykim4169 | 김지윤 | STT | 음성 답변/STT 적재 | `PATCH or POST /answers/{id}/stt` | `{stt_text}` | 200, answer_text=stt, source=stt | (미실행) | (실행필요) | 백엔드는 STT 결과 저장만(음성엔진 없음) |
| JY-07 | jykim4169 | 김지윤 | 꼬리질문 | 답변 기반 꼬리질문 | `POST /answers/{id}/followup` | STT 답변 | GENERATE_FOLLOWUP/NEXT_QUESTION | (미실행) | **MOCK** | - |
| JY-08 | jykim4169 | 김지윤 | 평가 | 평가/강점/약점 태그 | `GET /evaluations/{id}` + tags | answer_id | 200 | (미실행) | (실행필요) | OpenAI 직접(real) |
| JY-09 | jykim4169 | 김지윤 | 리포트 | 최종 리포트 | `GET /sessions/{id}/report` | session_id | 200 | (미실행) | (실행필요) | - |
| JY-10 | jykim4169 | 김지윤 | 관리자대조 | 페르소나/프롬프트 변경이 질문에 반영 | admin 페르소나 active-template 변경 후 질문 생성 | - | 변경 반영 | (미실행) | **NC** | mock 엔진이 admin 템플릿을 실제 참조하는지 확인 필요 |

---

## 3) 홍지윤 — 경력1년/비전공, 데이터분석 백엔드, text, verify 페르소나 (데이터 파이프라인)

JD 키워드: 데이터 전처리, AI Hub, Worknet API, Django, PostgreSQL/MySQL, Pinecone, 분석 파이프라인

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| HY-01 | h2yoon423 | 홍지윤 | 인증 | 회원가입/로그인 | signup→(verify)→login | 경력/비전공 | 토큰 발급 | (미실행) | (실행필요) | verify-email 미구현 블로커 공통 |
| HY-02 | h2yoon423 | 홍지윤 | 프로필 | 프로필 등록(경력 1년) | `POST /users/me/profile` | 경력연차=1 | 201 | (미실행) | (실행필요) | 경력 필드 스키마 확인 |
| HY-03 | h2yoon423 | 홍지윤 | JD | JD AI 분석 | `POST /analysis/analyze/` | 데이터 파이프라인 JD | PROCESSING→COMPLETED | (미실행) | (실행필요) | 실제 임베딩+Pinecone(real). 키/쿼터 BLOCKED 가능 |
| HY-04 | h2yoon423 | 홍지윤 | 매칭 | JD-이력서-자소서 매칭 가능 여부 | `POST /analysis/match/` | jd+resume+cover | 매칭 점수 | (미실행) | **NC** | match_service rule_score/years TODO. project_service 미구현 |
| HY-05 | h2yoon423 | 홍지윤 | 세션 | 세션 생성 | `POST /sessions` | mode=text, persona=verify | 201 | (미실행) | (실행필요) | - |
| HY-06 | h2yoon423 | 홍지윤 | 질문 | 질문 생성 | `POST /sessions/{id}/questions/generate` | - | 질문 | (미실행) | **MOCK** | - |
| HY-07 | h2yoon423 | 홍지윤 | 답변 | 답변 제출 | `POST /answers` | 텍스트 | 201 | (미실행) | (실행필요) | - |
| HY-08 | h2yoon423 | 홍지윤 | 평가 | 평가 결과 | `GET /evaluations/{id}` | - | 200 | (미실행) | (실행필요) | real OpenAI |
| HY-09 | h2yoon423 | 홍지윤 | 리포트 | 최종 리포트 | `GET /sessions/{id}/report` | - | 200 | (미실행) | (실행필요) | - |
| HY-10 | h2yoon423 | 홍지윤 | 관리자대조 | 관리자 회원목록에 활동 기록 | `GET /admin/members` (admin) | - | 홍지윤 계정/활동 확인 | (미실행) | (실행필요) | members 응답에 활동 메트릭 포함 여부 확인 |

---

## 4) 관리자 — tripdotzip

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| AD-01 | tripdotzip | 관리자 | 권한 | 관리자 권한 확인 | admin 토큰 발급 | is_staff/role=admin | 관리자 API 접근 가능 | (미실행) | (실행필요) | 계정 role/is_staff 설정 선행 |
| AD-02 | tripdotzip | 관리자 | 회원 | 회원 목록 조회 | `GET /admin/members` | - | 200, 박/김/홍 포함 | (미실행) | (실행필요) | - |
| AD-03 | tripdotzip | 관리자 | 회원 | 세 팀원 생성/로그인/활동 확인 | members 조회 | - | 3계정 식별 | (미실행) | (실행필요) | 활동기록 필드 범위 확인 |
| AD-04 | (더미) | QA더미 | 회원 | 상태 active/suspended 변경 | `PATCH /admin/members/{id}/status` | status=suspended | 200, 상태 변경 | (미실행) | (실행필요) | **팀원 계정 직접 변경 금지** → QA 더미만 |
| AD-05 | tripdotzip | 관리자 | 페르소나 | 페르소나 목록 | `GET /admin/personas` | - | 200 | (미실행) | (실행필요) | - |
| AD-06 | tripdotzip | 관리자 | 프롬프트 | 템플릿 생성 | `POST /admin/prompt-templates` | 템플릿 | 201 | (미실행) | (실행필요) | - |
| AD-07 | tripdotzip | 관리자 | 프롬프트 | 버전 생성 | `POST /admin/prompt-templates/{id}/versions` | 버전 | 201 | (미실행) | (실행필요) | - |
| AD-08 | tripdotzip | 관리자 | 프롬프트 | 기본 버전 변경 | `PATCH /admin/prompt-templates/{id}/default-version` | version_id | 200 | (미실행) | (실행필요) | - |
| AD-09 | tripdotzip | 관리자 | 페르소나 | 활성 템플릿 변경 | `PATCH /admin/personas/{id}/active-template` | template_id | 200 | (미실행) | (실행필요) | - |
| AD-10 | tripdotzip | 관리자 | 프롬프트 | 템플릿 삭제 | `DELETE /admin/prompt-templates/{id}` | template_id | 204 | (미실행) | (실행필요) | - |
| AD-11 | tripdotzip | 관리자 | Audit | audit log 기록 확인 | `GET /admin/audit-logs` | - | 위 변경 이력 기록됨 | (미실행) | (실행필요) | 변경 작업이 audit에 남는지 |
| AD-12 | parksoyun9084 | 박소윤 | 권한 | 일반 토큰 admin 접근 차단 | `GET /admin/audit-logs` (user token) | - | 403 | (미실행) | (실행필요) | IsAdminUserOrRole |

> persona_id/template_id 는 정수(int) PK, jd/resume/session/answer 는 UUID — 입력 데이터 작성 시 타입 주의.

---

## 5) 사용자 페르소나 임시계정 시나리오 (4종)

> ⚠️ 임시 계정 `careerzip.qa.*@gmail.com` 은 **실제 구글 계정 존재 미확인**. Google OAuth 미구현 → OAuth 검증은 BLOCKED.
> 대체: 이메일/비밀번호 가입 + `is_verified=True` 수동 처리 후 로그인하여 프로필~리포트 진행.

### 5-1) 김햄찌 — 비전공 신입 / 백엔드 / text / verify (압박 꼬리질문·CS 약점 검증)

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| KH-01 | careerzip.qa.kimhamzzi | 김햄찌 | 인증 | 계정 생성(대체) | signup→verified→login | 비전공/신입 | 토큰 발급 | (미실행) | BLOCKED | OAuth 미구현, 실계정 미확인 |
| KH-02 | careerzip.qa.kimhamzzi | 김햄찌 | 프로필 | 비전공 신입 프로필 저장 | `POST /users/me/profile` | 신입/비전공/백엔드 | 201 | (미실행) | (실행필요) | 전공/배경 필드 스키마 |
| KH-03 | careerzip.qa.kimhamzzi | 김햄찌 | 질문 | CS 기초 질문 생성 | `POST /sessions/{id}/questions/generate` | JD:Python,Django,CS기초 | 질문 | (미실행) | MOCK_ONLY | - |
| KH-04 | careerzip.qa.kimhamzzi | 김햄찌 | 답변 | 얕은/모호 답변 제출 | `POST /answers` | 개념 모호 답변 | 201 | (미실행) | (실행필요) | - |
| KH-05 | careerzip.qa.kimhamzzi | 김햄찌 | 꼬리질문 | verify 압박 꼬리질문 | `POST /answers/{id}/followup` | 모호 답변 | GENERATE_FOLLOWUP | (미실행) | MOCK_ONLY | mock이 답변 기반 분기하는지 |
| KH-06 | careerzip.qa.kimhamzzi | 김햄찌 | 평가 | CS/구체성 부족 약점 태그 | `GET /evaluations/{id}/weakness-tags` | answer_id | 약점 태그 생성 | (미실행) | (실행필요) | real OpenAI |
| KH-07 | careerzip.qa.kimhamzzi | 김햄찌 | 리포트 | CS 기초 보완 제안 | `GET /sessions/{id}/report` | session_id | 보완 제안 포함 | (미실행) | (실행필요) | 리포트 제안 로직 확인 |

### 5-2) 홍이찌 — 비전공 경력3년(SI) / 백엔드 / text / practical (경력 구조화·매칭)

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| HI-01 | careerzip.qa.hongizzi | 홍이찌 | 인증 | 계정 생성(대체) | signup→verified→login | 경력/비전공 | 토큰 | (미실행) | BLOCKED | OAuth 미구현 |
| HI-02 | careerzip.qa.hongizzi | 홍이찌 | 프로필 | 경력/비전공 프로필 저장 | `POST /users/me/profile` | 경력=3, SI | 201 | (미실행) | (실행필요) | - |
| HI-03 | careerzip.qa.hongizzi | 홍이찌 | 매칭 | JD 매칭 분석 가능 여부 | `POST /analysis/match/` | Java/Spring JD+이력서 | 매칭 점수 | (미실행) | NEEDS_CONFIRMATION | project_service 미구현 영향 |
| HI-04 | careerzip.qa.hongizzi | 홍이찌 | 평가 | SI 경험-서비스직무 연결 평가 | `GET /evaluations/{id}` | 성과수치 부족 답변 | 평가 | (미실행) | (실행필요) | real OpenAI |
| HI-05 | careerzip.qa.hongizzi | 홍이찌 | 꼬리질문 | practical 실무형 꼬리질문 | `POST /answers/{id}/followup` | answer_id | FOLLOWUP/NEXT | (미실행) | MOCK_ONLY | - |
| HI-06 | careerzip.qa.hongizzi | 홍이찌 | 리포트 | 경력 어필/성과 구체화 피드백 | `GET /sessions/{id}/report` | - | 피드백 포함 | (미실행) | (실행필요) | - |

### 5-3) 박쮜 — 전공 신입 / 프론트엔드 / voice / coach (STT·STAR 구조)

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| PJ-01 | careerzip.qa.parkjwi | 박쮜 | 인증 | 계정 생성(대체) | signup→verified→login | 전공/신입 | 토큰 | (미실행) | BLOCKED | OAuth 미구현 |
| PJ-02 | careerzip.qa.parkjwi | 박쮜 | 프로필 | 전공 신입 프로필 저장 | `POST /users/me/profile` | 전공/FE | 201 | (미실행) | (실행필요) | - |
| PJ-03 | careerzip.qa.parkjwi | 박쮜 | 세션 | voice 세션 생성 | `POST /sessions` | voice/coach | 201 | (미실행) | (실행필요) | - |
| PJ-04 | careerzip.qa.parkjwi | 박쮜 | STT | STT 결과 적재 | `PATCH /answers/{id}/stt` | {stt_text} | 200 source=stt | (미실행) | (실행필요) | FE는 브라우저 Web Speech |
| PJ-05 | careerzip.qa.parkjwi | 박쮜 | 평가 | STAR 구조 부족 약점 태그 | `GET /evaluations/{id}/weakness-tags` | STAR 미흡 답변 | 약점 태그 | (미실행) | (실행필요) | - |
| PJ-06 | careerzip.qa.parkjwi | 박쮜 | 꼬리질문 | coach 힌트형 꼬리질문 | `POST /answers/{id}/followup` | answer_id | FOLLOWUP | (미실행) | MOCK_ONLY | 페르소나별 톤 차이 mock 반영 여부 |
| PJ-07 | careerzip.qa.parkjwi | 박쮜 | 리포트 | 답변 구조화 개선 피드백 | `GET /sessions/{id}/report` | - | 피드백 포함 | (미실행) | (실행필요) | - |

### 5-4) 박일찌 — 비전공 경력4년 직무전환 / PM·기획 / text / verify (직무전환 스토리)

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| PI-01 | careerzip.qa.parkilzzi | 박일찌 | 인증 | 계정 생성(대체) | signup→verified→login | 경력/비전공/전환 | 토큰 | (미실행) | BLOCKED | OAuth 미구현 |
| PI-02 | careerzip.qa.parkilzzi | 박일찌 | 프로필 | 직무전환 프로필 저장 | `POST /users/me/profile` | 경력=4, 마케팅→PM | 201 | (미실행) | (실행필요) | 희망직무=PM/기획 처리 |
| PI-03 | careerzip.qa.parkilzzi | 박일찌 | 평가 | 경력-JD 연결 약함 약점 태그 | `GET /evaluations/{id}/weakness-tags` | 연결 모호 답변 | 약점 태그 | (미실행) | (실행필요) | - |
| PI-04 | careerzip.qa.parkilzzi | 박일찌 | 꼬리질문 | verify 근거 확인형 꼬리질문 | `POST /answers/{id}/followup` | answer_id | FOLLOWUP | (미실행) | MOCK_ONLY | - |
| PI-05 | careerzip.qa.parkilzzi | 박일찌 | 리포트 | 직무전환 스토리 개선 방향 | `GET /sessions/{id}/report` | - | 개선 방향 포함 | (미실행) | (실행필요) | Soft Skill→적합성 반영 여부 |

> 페르소나 의도(verify=압박/근거확인, coach=힌트형, practical=실무형)가 **현재 mock 엔진에서 실제로 차별화되는지** 는 별도 확인 필요(NEEDS_CONFIRMATION). real 엔진 전환 후 재검증 권장.

---

## 6) Frontend 화면 ↔ API 연결 (수동 QA)

| ID | 계정 | 사용자 | 구분 | 테스트 기능 | 시나리오 | 입력 데이터 | 예상 결과 | 실제 결과 | 상태 | 담당 확인 필요 |
|---|---|---|---|---|---|---|---|---|---|---|
| FE-01 | - | 공통 | FE인증 | 회원가입 화면 실연동 | `/signup` 입력→제출 | 폼 | BE signup 호출 | (미실행) | MOCK_ONLY | authApi 빈파일, mock 토큰 |
| FE-02 | - | 공통 | FE인증 | 로그인 화면 실연동 | `/login` | 폼 | BE login 호출 | (미실행) | MOCK_ONLY | API-first+mock fallback |
| FE-03 | - | 공통 | FE인증 | 구글 로그인 버튼 | 소셜 버튼 클릭 | - | OAuth 시작 | (미실행) | NOT_IMPLEMENTED | "mock입니다" 토스트 |
| FE-04 | - | 공통 | FE입력 | JD 입력 live 화면 | `/jd` 제출 | JD 텍스트 | `POST /jds` 호출 | (미실행) | (실행필요) | JdInputPage+jdApi |
| FE-05 | - | 공통 | FE입력 | 이력서/자소서/프로젝트 화면 | `/data/*` | 폼 | BE 호출 | (미실행) | MOCK_ONLY | 프로토타입 |
| FE-06 | - | 공통 | FE면접 | 면접 live 화면 | `/interview` 진행 | 세션 | MVP 흐름 전체 호출 | (미실행) | (실행필요) | VoiceInterviewPage+useInterview |
| FE-07 | - | 공통 | FE면접 | voice STT/TTS | `/interview` 음성 | 마이크 | Web Speech STT/TTS | (미실행) | (실행필요) | 브라우저(Chrome) 의존, 수동 |
| FE-08 | - | 공통 | FE리포트 | 리포트 화면 | `/report/*` | - | 리포트 표시 | (미실행) | MOCK_ONLY | 화면 프로토타입 |
| FE-09 | - | 공통 | FE마이페이지 | 면접 기록 화면 | `/mypage/interviews` | - | 기록 표시 | (미실행) | MOCK_ONLY | 프로토타입 |
| FE-10 | tripdotzip | 관리자 | FE관리자 | 관리자 live 화면 | `/admin/live/login→members→prompts` | admin 로그인 | adminApi 실호출 | (미실행) | (실행필요) | PrivateRoute(localStorage token) |
| FE-11 | tripdotzip | 관리자 | FE관리자 | audit log 화면 | `/admin/audit-logs` | - | audit 표시 | (미실행) | NOT_IMPLEMENTED | adminApi에 audit-logs 호출 없음 |
| FE-12 | - | 공통 | FE인증 | 401 자동 토큰 갱신 | 만료 access로 요청 | - | refresh 후 재시도 | (미실행) | NOT_IMPLEMENTED | axios 401 인터셉터 없음 |

---

# 📌 v2.0 — 확장 컬럼 테스트 케이스 (선행 조건 / 필요 데이터 / BLOCKED 사유 / 담당자)

> 모든 BLOCKED 사유의 1차 원인은 **access token 미발급 + 사용자 데이터 부재**. seed(1안) 또는 verify-email+메일(2안) 선행 시 대부분 해제.

| ID | 계정 | 사용자 | 기능 | 선행 조건 | 필요한 데이터 | 테스트 시나리오 | 예상 결과 | 현재 실제 결과 | 상태 | BLOCKED 사유 | 담당자 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V2-AUTH-01 | parksoyun9084 | 박소윤 | 회원가입 | - | email/name/pw | POST /auth/signup | 201 + user_id | (미실행) | PASS(실행필요) | - | 박소윤 |
| V2-MAIL-01 | parksoyun9084 | 박소윤 | 가입 환영 메일 | EMAIL 설정 | SMTP | 가입 후 환영 메일 수신 | 메일 도착 | (미실행) | NOT_IMPLEMENTED | 발송 코드/설정 없음 | 박소윤 |
| V2-MAIL-02 | tripdotzip | 관리자 | 신규가입 알림 메일 | ADMIN_NOTIFICATION_EMAIL | SMTP | 가입 시 관리자 메일 수신(민감정보 없음) | 메일 도착 | (미실행) | NOT_IMPLEMENTED | 미구현 | 박소윤 |
| V2-AUTH-02 | parksoyun9084 | 박소윤 | 이메일 인증 | verify-email 구현 | 인증 토큰 | GET /auth/verify-email | is_verified=True | (미실행) | NOT_IMPLEMENTED | 라우트 부재 | 박소윤 |
| V2-AUTH-03 | parksoyun9084 | 박소윤 | 로그인/토큰 | is_verified=True | seed 계정 | POST /auth/login | 200 + access_token + refresh cookie | (미실행) | BLOCKED | 신규계정 인증 불가 | 박소윤 |
| V2-AUTH-04 | careerzip.qa.* | 페르소나 | Google OAuth | OAuth 구현+실계정 | 구글 계정 | OAuth 로그인 | 토큰 발급 | (미실행) | BLOCKED | BE/FE 미구현+실계정 미확인 | 박소윤 |
| V2-PROF-01 | jykim4169 | 김지윤 | 프로필 등록 | access token | profile | POST /users/me/profile | 201 | (미실행) | BLOCKED | 토큰 없음 | 박소윤 |
| V2-JD-01 | h2yoon423 | 홍지윤 | JD 등록 | access token | JD 텍스트 | POST /jds | 201 + jd_id | (미실행) | BLOCKED | 토큰 없음 | 박소윤 |
| V2-JD-02 | h2yoon423 | 홍지윤 | JD 분석 | jd_id + OpenAI/Pinecone | jd_id | POST /analysis/analyze/ | PROCESSING→COMPLETED | (미실행) | BLOCKED / NC | 토큰·jd_id 부재 + 명세 경로 불일치 | 홍지윤 |
| V2-SES-01 | parksoyun9084 | 박소윤 | 세션 생성 | access token+profile | mode/persona | POST /sessions | 201 + session_id | (미실행) | BLOCKED | 토큰/프로필 부재 | 박소윤 |
| V2-Q-01 | parksoyun9084 | 박소윤 | 질문 생성 | session_id | session | POST /sessions/{id}/questions/generate | 질문 3개 | (미실행) | BLOCKED→MOCK_ONLY | 토큰/세션 부재; 엔진 mock 기본 | 김지윤 |
| V2-FU-01 | jykim4169 | 김지윤 | 꼬리질문 | answer_id | answer | POST /answers/{id}/followup | FOLLOWUP/NEXT 분기 | (미실행) | BLOCKED→MOCK_ONLY | answer 부재; mock | 김지윤 |
| V2-EV-01 | 박은지대상 | - | 평가 | answer_id+OpenAI키 | answer | GET /evaluations/{answer_id} | 200 평가 | (미실행) | BLOCKED→REAL | answer 부재; 키/쿼터 | 박은지 |
| V2-RP-01 | parksoyun9084 | 박소윤 | 최종 리포트 | 평가 완료 | session/eval | GET /sessions/{id}/report | 200 리포트 | (미실행) | BLOCKED | 선행 전부 차단 | 박은지 |
| V2-MY-01 | parksoyun9084 | 박소윤 | 마이페이지 | session/report | 기록 | GET /mypage/interviews | 200 기록 | (미실행) | BLOCKED | 데이터 없음 | 박소윤 |
| V2-AD-01 | tripdotzip | 관리자 | 회원목록 | admin 토큰 | admin 권한 | GET /admin/members | 200 목록 | (미실행) | BLOCKED | admin 계정/권한 없음 | 김이선 |
| V2-AD-02 | tripdotzip | 관리자 | audit log | admin 토큰 | audit | GET /admin/audit-logs | 200 | (미실행) | BLOCKED | 〃 | 김이선 |
| V2-AD-03 | tripdotzip | 관리자 | 프롬프트/버전 | admin 토큰 | template | 생성→버전→기본변경 후 질문 생성 반영 확인 | 반영됨 | (미실행) | BLOCKED→NC | 토큰 없음; 반영 여부 확인 필요 | 김이선 |
| V2-SEC-01 | parksoyun9084 | 박소윤 | 데이터 격리 | 2계정 토큰 | 타인 자원 id | 타 사용자 jd/resume/session 조회 | 404 | (미실행) | BLOCKED | 토큰 없음 | 박소윤 |

---
# ✅ v2.1 구현 후 상태 갱신
| ID | 기능 | 이전 | 현재 | 근거 |
|---|---|---|---|---|
| AUTH-04 / V2-AUTH-02 | verify-email | NOT_IMPLEMENTED | **PASS** | test_verify_email_* 통과 |
| AUTH-09 | logout | NOT_IMPLEMENTED | **PASS** | test_logout_* 통과 |
| AUTH-05 / V2-AUTH-03 | 로그인 access token | BLOCKED | **PASS** | test_..._login_issues_token 통과 |
| AUTH-07 | token refresh | (실행필요) | **PASS** | test_token_refresh_success 통과 |
| V2-MAIL-01 | 환영 메일 | NOT_IMPLEMENTED | **PASS** | test_signup_sends_*_emails 통과 |
| V2-MAIL-02 | 관리자 알림 메일 | NOT_IMPLEMENTED | **PASS** | 동일 테스트, 민감정보 미포함 검증 |
| SEC-02 | 일반→admin API 403 | (실행필요) | **PASS** | test_normal_user_cannot_access_admin_api |
| AUTH-06 | Google OAuth | NOT_IMPLEMENTED | NOT_IMPLEMENTED(후순위) | FE 버튼 비활성 처리 |
| SY-18 등 | 질문 생성 | MOCK_ONLY | MOCK_ONLY | 엔진 기본 mock 유지 |
| 프로필~리포트~관리자 | 후속 흐름 | BLOCKED | **READY**(seed/verify 후 실행) | 토큰 블로커 해소 |
