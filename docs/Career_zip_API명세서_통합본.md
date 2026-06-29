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

## 사용자 설정 인재상 API

Base path: `/api/v1`

### GET `/talent-profiles/catalog`

인증: 필요.

활성화된 인재상 상위 영역과 세부 인재상을 `display_order` 오름차순으로 조회한다.

Response 200:

```json
{
  "categories": [
    {
      "category_id": 1,
      "category_code": "EXECUTION_RESPONSIBILITY",
      "category_name": "실행과 책임",
      "short_description": "목표를 행동과 결과로 연결하고 맡은 일에 끝까지 책임지는 역량",
      "display_order": 1,
      "traits": [
        {
          "trait_id": 1,
          "trait_code": "OWNERSHIP",
          "trait_name": "주도성",
          "short_description": "지시를 기다리지 않고 필요한 문제를 스스로 발견해 행동하는 역량",
          "display_order": 1
        }
      ]
    }
  ]
}
```

Validation:

- `TalentProfileCategory.is_active=true`
- `TalentProfileTrait.is_active=true`

### GET `/jds/{jd_id}/talent-profile`

인증: 필요. 본인 소유 JD만 조회 가능.

Path Parameter:

- `jd_id`: UUID

설정이 없으면 404가 아니라 다음처럼 200을 반환한다.

```json
{
  "jd_id": "00000000-0000-0000-0000-000000000000",
  "profile": null
}
```

설정이 있으면 다음 구조를 반환한다.

```json
{
  "jd_id": "00000000-0000-0000-0000-000000000000",
  "source_type": "USER_DEFINED",
  "source_text": null,
  "custom_summary": "빠르게 실행하고 결과를 기반으로 개선하는 문화를 중요하게 생각합니다.",
  "confirmed_by_user": true,
  "confirmed_at": "2026-06-29T12:00:00+09:00",
  "items": [
    {
      "trait_id": 1,
      "trait_code": "OWNERSHIP",
      "trait_name": "주도성",
      "category_code": "EXECUTION_RESPONSIBILITY",
      "category_name": "실행과 책임",
      "priority_order": 1,
      "custom_description": "문제를 먼저 발견하고 해결 방법을 제안하는 사람"
    }
  ]
}
```

Error Code:

- 401: 인증 필요
- 404: JD가 없거나 본인 소유가 아님

### PUT `/jds/{jd_id}/talent-profile`

인증: 필요. 본인 소유 JD만 수정 가능.

Path Parameter:

- `jd_id`: UUID

Request:

```json
{
  "source_type": "USER_DEFINED",
  "source_text": null,
  "custom_summary": "빠르게 실행하고 결과를 기반으로 개선하는 문화를 중요하게 생각합니다.",
  "confirmed_by_user": true,
  "items": [
    {
      "trait_code": "OWNERSHIP",
      "priority_order": 1,
      "custom_description": "문제를 먼저 발견하고 해결 방법을 제안하는 사람"
    }
  ]
}
```

Validation:

- `items` 최소 1개, 최대 5개
- `trait_code` 중복 금지
- `priority_order` 중복 금지
- `priority_order`는 1부터 선택 개수까지 연속값
- 비활성 또는 존재하지 않는 trait 선택 불가
- `custom_description` 최대 500자
- `source_type`은 `OFFICIAL`, `AI_EXTRACTED`, `USER_DEFINED`, `JOB_DEFAULT`, `HYBRID` 중 하나

동작:

- 전체 교체 방식으로 저장한다.
- 저장은 transaction으로 처리하며 일부 항목 실패 시 기존 상태를 유지한다.
- `confirmed_by_user=false` 임시 저장은 허용하지만 질문 생성에는 사용하지 않는다.
- `confirmed_by_user`가 `false -> true`가 되면 `confirmed_at`을 현재 시각으로 저장한다.
- `confirmed_by_user`가 `true -> false`가 되면 `confirmed_at=null`로 변경한다.

Error Code:

- 400: validation error
- 401: 인증 필요
- 404: JD가 없거나 본인 소유가 아님

표현 정책:

사용자 설정 인재상은 회사 공식 인재상으로 표현하지 않는다. 화면과 프롬프트에서는 반드시 `사용자가 면접 연습을 위해 설정한 인재상 기준`으로 표현한다.
| --- | --- |
| 사용자 대표 GitHub 표시 | `input_userprofile.github_url` |
| 선택 이력서 대표/참고 GitHub | `input_resumemaster.github_url` |
| 실제 Repository 분석/프로젝트 기반 질문 | `input_projectexperience.github_url` 우선 |

현재 `ProjectExperience`는 `User`에만 연결되어 있고 `ResumeMaster`와 직접 연결되어 있지 않다. 복수 이력서에서 프로젝트 포함 관계를 구분하려면 `ProjectExperience -> ResumeMaster` FK 또는 중간 테이블 추가 승인이 필요하다. 승인 전에는 모든 프로젝트를 선택 이력서의 프로젝트로 간주하지 않는다.

## ���� ���ε� ���巹�� API

Base path: `/api/v1`

### `POST /documents/upload`

���� ���� ���ε� API�Դϴ�. JWT ������ �ʿ��ϸ� `multipart/form-data`�� �����մϴ�.

Request fields:

| field | type | required | description |
| --- | --- | --- | --- |
| `file` | binary | yes | PDF �Ǵ� DOCX, �ִ� 10MB |
| `document_type` | string | yes | `resume`, `cover_letter`, `jd`, `portfolio`, `other` |

ó�� ��Ģ: ���� ����, MIME, �ñ״�ó, �ջ�/��ȣȭ/��ũ��, �ؽ�Ʈ ����, �ּ� ����, ���� ����, ������ ������ ��� ����� �ڿ��� DB�� FileField�� �����մϴ�. TXT�� �������� �ʽ��ϴ�. OCR ������ ���� �������� �ʾ�����, �ؽ�Ʈ�� ���� PDF�� `OCR_NOT_SUPPORTED`�� �����մϴ�. DOCX ��ũ�� Ž���� ���� ���� �˻��̸� �Ϲ� �ֿ��� �˻縦 �ǹ����� �ʽ��ϴ�.

Success: `201 Created`

```json
{
  "document_id": "uuid",
  "document_type": "resume",
  "original_filename": "resume.pdf",
  "file_type": "pdf",
  "file_size": 12345,
  "parse_status": "completed",
  "extracted_text": "...",
  "error_message": ""
}
```

### `POST /jds/upload`

JD ���� ���ε� API�Դϴ�. JWT ������ �ʿ��ϸ� PDF�� DOCX�� ����մϴ�. ���� ��� �� `JobDescription.original_text`�� ���� �ؽ�Ʈ�� �����մϴ�. ���� �� ������ ȣȯ�� ������ `input_method`�� ���� `PDF` ���� �����մϴ�.

Request fields: `file` required, `company_name` optional, `position` optional.

### `POST /resumes/upload`

�̷¼� ���� ���ε� API�Դϴ�. JWT ������ �ʿ��ϸ� PDF�� DOCX�� ����մϴ�. ���� ��� �� `ResumeMaster.original_text`�� ���� �ؽ�Ʈ�� �����մϴ�.

Request fields: `file` required, `name` optional.

### Error Response

```json
{
  "error_code": "DOCUMENT_TOO_SHORT",
  "message": "�м��ϱ⿡ ���� ������ �ʹ� ª���ϴ�.",
  "detail": "�м��ϱ⿡ ���� ������ �ʹ� ª���ϴ�.",
  "code": "DOCUMENT_TOO_SHORT"
}
```

| HTTP | error_code | description |
| ---: | --- | --- |
| 400 | `INVALID_FILE_TYPE` | PDF �Ǵ� DOCX�� �ƴϰų� MIME�� ������ ���� |
| 400 | `INVALID_FILE_SIGNATURE` | Ȯ���ڿ� ���� ���� �ñ״�ó/������ ���� ���� |
| 400 | `FILE_EMPTY` | 0����Ʈ ���� |
| 413 | `FILE_TOO_LARGE` | 10MB �ʰ� |
| 422 | `DOCUMENT_CORRUPTED` | �ջ�Ǿ� �� �� ���� |
| 422 | `DOCUMENT_ENCRYPTED` | ��ȣȭ �Ǵ� ��й�ȣ PDF |
| 422 | `DOCUMENT_MACRO_DETECTED` | DOCX ���� ��ũ�� Ž�� |
| 422 | `TEXT_EXTRACTION_FAILED` | �ؽ�Ʈ ���� ���� �Ǵ� DOCX �ؽ�Ʈ ���� |
| 422 | `DOCUMENT_TOO_SHORT` | �ּ� ���� �� �̴� |
| 422 | `DOCUMENT_TYPE_MISMATCH` | ������ ���԰� ���� ���� ���� ����ġ |
| 422 | `DOCUMENT_NOT_RELEVANT` | ���� �غ� ������ ���� ����� |
| 422 | `UNSAFE_DOCUMENT_CONTENT` | ������Ʈ �����Ǽ� ���� �� ���� ���� |
| 422 | `OCR_NOT_SUPPORTED` | �̹���/��ĵ PDF�� OCR �ʿ������� ������ |
## Document Upload Guardrail API

Base path: `/api/v1`

### `POST /documents/upload`

Generic document upload endpoint. JWT authentication is required and the request must be `multipart/form-data`.

Request fields:

| field | type | required | description |
| --- | --- | --- | --- |
| `file` | binary | yes | PDF or DOCX, max 10MB |
| `document_type` | string | yes | `resume`, `cover_letter`, `jd`, `portfolio`, `other` |

Processing rule: the file is saved to DB/FileField only after extension, MIME type, file signature, corruption/encryption/macro checks, text extraction, minimum length, document type, relevance, and safety checks all pass. TXT is not supported. OCR is not integrated yet, so image-only PDFs fail with `OCR_NOT_SUPPORTED`. DOCX macro detection is a static structure check and is not a general malware scan.

Success: `201 Created`

```json
{
  "document_id": "uuid",
  "document_type": "resume",
  "original_filename": "resume.pdf",
  "file_type": "pdf",
  "file_size": 12345,
  "parse_status": "completed",
  "extracted_text": "...",
  "error_message": ""
}
```

### `POST /jds/upload`

JD upload endpoint. JWT authentication is required. PDF and DOCX are allowed. After validation succeeds, extracted text is saved to `JobDescription.original_text`. For compatibility with current model choices, `input_method` remains `PDF` for file uploads.

Request fields: `file` required, `company_name` optional, `position` optional.

### `POST /resumes/upload`

Resume upload endpoint. JWT authentication is required. PDF and DOCX are allowed. After validation succeeds, extracted text is saved to `ResumeMaster.original_text`.

Request fields: `file` required, `name` optional.

### Error Response

```json
{
  "error_code": "DOCUMENT_TOO_SHORT",
  "message": "????? ?? ??? ?? ????.",
  "detail": "????? ?? ??? ?? ????.",
  "code": "DOCUMENT_TOO_SHORT"
}
```

| HTTP | error_code | description |
| ---: | --- | --- |
| 400 | `INVALID_FILE_TYPE` | Extension or MIME type is not allowed |
| 400 | `INVALID_FILE_SIGNATURE` | Extension does not match actual file signature/structure |
| 400 | `FILE_EMPTY` | Empty file |
| 413 | `FILE_TOO_LARGE` | File exceeds 10MB |
| 422 | `DOCUMENT_CORRUPTED` | File cannot be opened or parsed |
| 422 | `DOCUMENT_ENCRYPTED` | Encrypted or password-protected PDF |
| 422 | `DOCUMENT_MACRO_DETECTED` | DOCX macro detected |
| 422 | `TEXT_EXTRACTION_FAILED` | Text extraction failed or DOCX has no text |
| 422 | `DOCUMENT_TOO_SHORT` | Extracted text is below the minimum length |
| 422 | `DOCUMENT_TYPE_MISMATCH` | Upload slot and actual document type do not match |
| 422 | `DOCUMENT_NOT_RELEVANT` | Document is not usable for interview preparation |
| 422 | `UNSAFE_DOCUMENT_CONTENT` | Prompt-injection-like or unsafe content detected |
| 422 | `OCR_NOT_SUPPORTED` | OCR is required for image-only PDF but not supported yet |
