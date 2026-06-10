# Career.zip 실제 데이터 기반 통합 E2E 체크리스트

> v1.0 · 2026-06-10 · 실행자가 직접 체크. `[ ]` 미수행 / `[x]` 통과 / `[!]` 실패·이슈
> 자동화 어려운 항목(구글 OAuth 등)은 **수동 QA** 표기. 토큰/비밀번호/쿠키 값은 기록 금지.

## A. 사전 준비
- [ ] `develop` 최신화 후 `feature/qa-real-data-e2e` 브랜치 생성 (현재 `.git/index.lock` 점유 중 → IDE git 프로세스 종료 후 진행)
- [ ] `.env.qa.local` 작성 (Git 미커밋 확인), 실제 AI QA 시 `INTERVIEW_AI_CHAIN_ENGINE=openai` + `INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=True`
- [ ] DB 대상 확인 — 현재 `.env`가 **원격 Aiven MySQL** 사용. QA 쓰기 시 운영 데이터 오염 주의, QA 식별자(`[QA]`) 부착
- [ ] QA 3계정 `is_verified=True` 수동 처리 방법 합의 (verify-email 미구현 때문)
- [ ] 관리자 계정 `tripdotzip` 의 `is_staff=True` 또는 `role='admin'` 설정 확인

## B. 인증 (반자동 API + 수동)
- [ ] 회원가입 성공 (201) — 박/김/홍 각 1회, `[QA]` 이름 사용
- [ ] 중복 회원가입 409
- [ ] 미인증 로그인 403 ("Email not verified")
- [ ] **이메일 인증 — verify-email 엔드포인트 미구현 확인** (NOT_IMPLEMENTED 기록)
- [ ] 로그인 성공 (verified 후) → access_token + refresh cookie 발급
- [ ] **구글 로그인 — 백엔드 OAuth 라우트 부재 확인** (수동 / 프론트 처리 여부 확인)
- [ ] access token 발급/갱신 (`/auth/token/refresh`) 200
- [ ] refresh cookie 없이 refresh → 401
- [ ] **로그아웃 엔드포인트 미구현 확인** (NOT_IMPLEMENTED)
- [ ] 무효/만료 토큰으로 보호 API 접근 → 401

## C. 사용자 데이터 격리 / 권한
- [ ] 박소윤 토큰으로 김지윤 `jd_id` 조회 → 404
- [ ] 박소윤 토큰으로 김지윤 `resume_id` 조회 → 404
- [ ] 박소윤 토큰으로 홍지윤 `session_id` 조회 → 404
- [ ] (명세가 403을 요구하면 **불일치 기록**: 구현은 404)
- [ ] 일반 사용자 토큰으로 `/admin/members`, `/admin/audit-logs` → 403

## D. 프로필
- [ ] 프로필 등록 / 조회 / 수정 (박/김/홍 각각)
- [ ] 홍지윤 경력연차=1 필드 정상 저장 확인

## E. JD
- [ ] JD 직접 입력 등록 `POST /jds` (계정별 비중복 JD)
- [ ] JD 목록/상세 조회
- [ ] JD 삭제 `DELETE /jds/{id}`
- [ ] **JD 업로드 경로 확인**: 명세 `POST /jds/upload` 부재 → 실제 `POST /documents/upload` (불일치 기록)
- [ ] **JD 분석 경로 확인**: 명세 `POST /jds/{id}/analyze` 부재 → 실제 `POST /analysis/analyze/` (불일치 기록)
- [ ] JD 분석 상태 PROCESSING → COMPLETED/FAILED 전이 확인
- [ ] **JD 매칭 미확정 확인**: `/analysis/match/` 존재하나 명세 미확정 (NEEDS_CONFIRMATION)

## F. 이력서 / 자소서 / 프로젝트
- [ ] 이력서 등록 + 학력/경력/스킬/자격 하위 등록
- [ ] **이력서 업로드 경로 확인**: 명세 `POST /resumes/upload` 부재 → `documents/upload` (불일치)
- [ ] 이력서 조회
- [ ] 자소서 등록 / 목록 / 상세
- [ ] 프로젝트 등록 / 수정 / 목록

## G. 면접 세션 / 질문 / 답변
- [ ] **면접 API 표면 확정**: 중첩형(`/interviews/...`) vs MVP 평면형 중 정식 확인 (NEEDS_CONFIRMATION)
- [ ] 세션 생성 (박:text/practical, 김:voice/coach, 홍:text/verify)
- [ ] 세션 조회 / 상태 변경
- [ ] 질문 생성 — **기본 mock 동작 확인** (MOCK_ONLY)
- [ ] (real 전환 시) 질문이 JD/이력서 키워드 반영하는지
- [ ] 질문 목록 조회
- [ ] 답변 제출 (text) `POST /answers`
- [ ] STT 결과 적재 (voice) — `stt_text` 저장, `answer_source=stt` 확인
- [ ] 꼬리질문 생성 또는 NEXT_QUESTION 분기 확인

## H. 평가 / 리포트 / 마이페이지
- [ ] 평가 조회 — **OpenAI 직접 호출(real)**, 키/쿼터 없으면 BLOCKED
- [ ] 강점 태그 / 약점 태그 조회
- [ ] 최종 리포트 조회 (BEI/CBI/Grounding 스키마 확인)
- [ ] 마이페이지 면접 기록 확인 `GET /mypage/interviews`

## I. 관리자
- [ ] 관리자 로그인/권한 확인
- [ ] 회원 목록에 박/김/홍 3계정 확인
- [ ] (QA 더미 계정으로만) active ↔ suspended 변경 — **팀원 계정 직접 변경 금지**
- [ ] 페르소나 목록 조회
- [ ] 프롬프트 템플릿 생성 → 버전 생성 → 기본 버전 변경 → 활성 템플릿 변경
- [ ] 템플릿 삭제
- [ ] 위 변경들이 audit-logs에 기록되는지 확인
- [ ] 일반 사용자 토큰 admin 접근 403

## J. 보안 / 개인정보 마감 점검
- [ ] 코드/로그/결과에 실제 비밀번호·인증코드·토큰·쿠키 값 없음
- [ ] `.env*` Git 미추적 확인 (`git status` 에 .env 미노출)
- [ ] QA 생성 데이터에 식별자 부착 및 정리 계획 수립
- [ ] 운영 DB 직접 수정 없음
- [ ] DB 구조 변경 필요 시 사유+migration 필요 여부만 보고 (임의 변경 금지)

## K. 수동 QA 전용 (프론트/OAuth)
- [ ] (수동) 구글 OAuth 로그인 화면 흐름 — 브라우저 직접 로그인, 자동화 스크립트에 비밀번호 미입력
- [ ] (수동) 프론트 화면에서 입력→세션→리포트 흐름 시각 확인 (프론트 레포 연결 후 Playwright 권장)

---

# 📌 v2.0 선행 차단 해제 체크리스트 (access token / 사용자 데이터 / 메일)

## L. 차단 해제(P0) — 이거 없이는 B~I 전부 진행 불가
- [ ] (택1) **1안 seed**: 팀원3+페르소나4+관리자 계정 생성, `is_verified=True`, 관리자 `is_staff=True or role=admin`, 기본 profile/JD/resume/session
- [ ] (택1) **2안 구현**: `GET /auth/verify-email` + 가입 시 환영/관리자/인증 메일 발송
- [ ] access token 실제 발급 확인(seed 또는 verify 후 로그인 200 + `access_token`)
- [ ] 관리자 `tripdotzip` 권한 확인(`is_staff/role=admin`) 및 admin 토큰 발급
- [ ] 원격 공유 DB ↔ QA DB 분리 또는 `[QA]` 식별자 정책 합의

## M. 메일 (운영 필수)
- [ ] EMAIL_* env 설정(.env 미커밋) 및 local/QA/prod 분리
- [ ] 가입 환영 메일 발송(HTML+텍스트 fallback)
- [ ] 관리자 신규가입 알림 메일 발송(민감정보 미포함: 비번/토큰/쿠키 없음)
- [ ] 이메일 인증 메일 발송 및 verify 흐름
- [ ] 메일 발송 실패 로그 / 회원가입 성공 유지 정책 확인
- [ ] (운영) Celery/Redis 비동기 발송 검토

## N. FE 실연동 선행
- [ ] `authApi.js`/`userStore.js` 구현(가입/로그인/로그아웃)
- [ ] `LoginPage` 실패 시 데모 자동진입 제거 → 에러 표면화
- [ ] `axiosInstance` `withCredentials:true` + 401 refresh 인터셉터
- [ ] 로그인 URL slash 정합(`/auth/login` vs `/auth/login/`)
- [ ] 회원가입 화면 실연동(현재 prototype only)

---
# ✅ v2.1 P0 구현 완료 체크 (feature/auth-token-email-recovery)
- [x] verify-email 구현 (GET /auth/verify-email, 서명 토큰 24h)
- [x] logout 구현 (POST /auth/logout, cookie 삭제)
- [x] 가입 환영 메일 발송 (HTML+text, 인증 링크)
- [x] 관리자 신규가입 알림 메일 (민감정보 미포함)
- [x] seed_qa_users 커맨드 (팀원/페르소나/관리자, verified)
- [x] 로그인 access_token + refresh cookie 발급 (테스트 통과)
- [x] FE /auth/login·/auth/signup·/verify-email 실연동 + withCredentials + 401 refresh
- [x] 테스트 16건 통과 / build OK
- [ ] (다음) 실제 SMTP(.env) 로 메일 도달 수동 확인
- [ ] (다음) seed 후 프로필~면접~평가~리포트 실행 E2E
- [ ] (BLOCKED) index.lock 해제 후 feature/auth-token-email-recovery 브랜치 커밋
