# Career.zip ERD

작성 기준: 2026-06-18

## Accounts

```text
accounts_user
- id PK
- email unique
- password
- name
- is_verified
- status
- is_staff
- is_active
- dormancy_warning_sent_at
- last_login
- created_at
- updated_at
```

```text
accounts_pending_registration
- id PK
- email unique
- password_hash
- name
- code_hash
- expires_at
- resend_available_at
- attempt_count
- max_attempts
- is_used
- verified_at
- terms_version
- privacy_version
- terms_agreed
- privacy_agreed
- marketing_agreed
- agreed_at
- created_at
- updated_at
```

```text
accounts_email_verification_code
- id PK
- user_id FK -> accounts_user.id
- code_hash
- expires_at
- attempt_count
- is_used
- created_at
```

`accounts_email_verification_code`는 legacy 미인증 User 호환을 위해 유지한다. 신규 회원가입은 `accounts_pending_registration`을 사용하며 인증 성공 후에만 `accounts_user`가 생성된다.

## Terms Agreement

기존 Backend 모델과 migration에서 `TermsAgreement`, `terms_agreements`, `UserConsent` 동일 목적 테이블은 확인되지 않았다. 중복 생성을 피하기 위해 이번 인증 PR에서는 Pending 단계의 약관 snapshot만 저장한다.

후속 `feature/terms-consent` PR에서 실제 이력 테이블을 추가할 경우 문서/ERD 기준 이름은 다음으로 확정한다.

```text
terms_agreements
- id PK
- user_id FK -> accounts_user.id
- terms_version
- privacy_version
- terms_agreed
- privacy_agreed
- marketing_agreed
- agreed_at
- withdrawn_at
- created_at
- updated_at
```

## Input/GitHub 관계

```text
input_userprofile
- id PK
- user_id OneToOne -> accounts_user.id
- github_url
```

```text
input_resumemaster
- id PK
- user_id FK -> accounts_user.id
- github_url
```

```text
input_projectexperience
- id PK
- user_id FK -> accounts_user.id
- project_name
- description
- contribution
- tech_stack
- github_url
```

현재 관계는 `ProjectExperience -> User`만 존재한다. `ProjectExperience -> ResumeMaster` 직접 FK는 없다.

승인 필요:

```text
현재 관계:
ProjectExperience -> User

문제:
복수 이력서 사용 시 어떤 프로젝트가 선택한 이력서에 포함되는지 구분 불가

제안:
ProjectExperience -> ResumeMaster 관계 추가
또는 ResumeProjectMapping 중간 테이블 추가

Migration 영향:
input_projectexperience에 nullable FK 추가 또는 신규 mapping 테이블 추가

API 영향:
프로젝트 생성/수정/조회와 면접 세션 생성 payload에 resume-project 매핑 규칙 추가 필요

Frontend 영향:
프로젝트 입력 화면에서 선택 이력서 또는 프로젝트 선택 UI 필요

기존 데이터 영향:
기존 프로젝트 row는 매핑 미확정 상태로 유지하고 자동 연결하지 않음

Rollback:
신규 FK/테이블 제거 전 참조 API 배포 롤백 필요
```
