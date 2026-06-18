# Career.zip API 명세서 통합본

작성 기준: 2026-06-18, Backend branch `fix/signup-create-user-after-verification`

## 인증/회원가입

Base path: `/api/v1/auth`

### POST `/signup`

회원가입 정보를 검증하고 `PendingRegistration`에 저장한 뒤 6자리 이메일 인증번호를 발송한다. 이 단계에서는 `accounts_user`를 생성하지 않으며 응답에 `user_id`를 반환하지 않는다.

Request body:

```json
{
  "email": "test@example.com",
  "name": "홍길동",
  "password": "StrongPw!234",
  "terms_version": "terms-2026-06",
  "privacy_version": "privacy-2026-06",
  "terms_agreed": true,
  "privacy_agreed": true,
  "marketing_agreed": false
}
```

Success: `201 Created`

```json
{
  "detail": "인증번호를 발송했습니다.",
  "expires_in": 600,
  "resend_after": 60
}
```

Pending 재요청이 쿨다운 중이면 `200 OK`와 `retry_after`를 반환할 수 있다. 기존 미인증 `User`는 legacy 인증번호 재발송 경로를 유지하지만 `user_id`는 반환하지 않는다.

Error codes:

| HTTP | code | 설명 |
| --- | --- | --- |
| 400 | validation error | 필수 입력값, 비밀번호 정책, 필수 약관 동의 실패 |
| 403 | ACCOUNT_BANNED | 차단된 계정 |
| 409 | EMAIL_ALREADY_REGISTERED | 이미 인증 완료된 이메일 |
| 409 | PENDING_REGISTRATION_EXISTS | 동시 요청으로 pending row가 이미 존재 |
| 503 | EMAIL_SEND_FAILED | SMTP 발송 실패. User는 생성되지 않음 |

### POST `/verify-email`

`PendingRegistration`과 인증번호를 검증하고 성공 시 하나의 transaction 안에서 실제 `User`를 생성한다. 비밀번호는 Pending에 저장된 Django password hash를 그대로 사용하며 재해시하지 않는다.

Request body:

```json
{
  "email": "test@example.com",
  "code": "123456"
}
```

Success: `200 OK`

```json
{
  "message": "이메일 인증이 완료되었습니다."
}
```

처리 순서:

1. `PendingRegistration` row lock
2. 만료, 시도 횟수, code hash 검증
3. `User` 중복 여부 재확인
4. `User` 생성 및 `is_verified=True`
5. Pending 사용 완료 표시

Error codes:

| HTTP | code | 설명 |
| --- | --- | --- |
| 404 | PENDING_REGISTRATION_NOT_FOUND | 인증 대기 데이터 없음 |
| 400 | VERIFY_CODE_INVALID | 인증번호 불일치 |
| 400 | VERIFY_CODE_EXPIRED | 인증번호 만료 |
| 429 | VERIFY_TOO_MANY_ATTEMPTS | 최대 시도 초과 |
| 409 | REGISTRATION_ALREADY_VERIFIED | 이미 사용 완료된 Pending |
| 409 | EMAIL_ALREADY_REGISTERED | transaction 중 User 중복 확인 |

### POST `/verify-email/resend`

Pending 기반 인증번호를 재발송한다. User를 생성하지 않는다.

Request body:

```json
{
  "email": "test@example.com"
}
```

Success: `200 OK`

```json
{
  "detail": "인증번호를 다시 발송했습니다.",
  "message": "인증번호를 다시 발송했습니다.",
  "expires_in": 600,
  "resend_after": 60
}
```

Error codes:

| HTTP | code | 설명 |
| --- | --- | --- |
| 404 | PENDING_REGISTRATION_NOT_FOUND | 인증 대기 데이터 없음 |
| 409 | REGISTRATION_ALREADY_VERIFIED | 이미 사용 완료된 Pending |
| 429 | RESEND_COOLDOWN | 재전송 쿨다운 |
| 503 | EMAIL_SEND_FAILED | SMTP 발송 실패 |

### Legacy `POST /resend-verification`

기존 미인증 `User` 호환용 alias다. 신규 회원가입은 `/verify-email/resend`를 사용한다. legacy 데이터는 자동 삭제하거나 Pending으로 자동 변환하지 않는다.

## 입력 데이터와 GitHub URL 의미

| 목적 | 기준 컬럼 |
| --- | --- |
| 사용자 대표 GitHub 표시 | `input_userprofile.github_url` |
| 선택 이력서 대표/참고 GitHub | `input_resumemaster.github_url` |
| 실제 Repository 분석/프로젝트 기반 질문 | `input_projectexperience.github_url` 우선 |

현재 `ProjectExperience`는 `User`에만 연결되어 있고 `ResumeMaster`와 직접 연결되어 있지 않다. 복수 이력서에서 프로젝트 포함 관계를 구분하려면 `ProjectExperience -> ResumeMaster` FK 또는 중간 테이블 추가 승인이 필요하다. 승인 전에는 모든 프로젝트를 선택 이력서의 프로젝트로 간주하지 않는다.
