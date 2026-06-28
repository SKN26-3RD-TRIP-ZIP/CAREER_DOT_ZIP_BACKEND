# Career_Dot_Zip
Final Project - 모의면접 시스템

## Email Verification API

Base path: `/api/v1/auth`

- `POST /signup`
  - Public endpoint. Creates or updates `PendingRegistration` and sends a 6-digit verification code.
  - It does not create `accounts_user` and does not return `user_id`.
  - Success: `201` with `detail`, `expires_in=600`, `resend_after=60`.
  - Verification email send failure: `503` with `code=EMAIL_SEND_FAILED`.
- `POST /verify-email`
  - Public endpoint. Body: `{ "email": "...", "code": "123456" }`.
  - Success: `200`. Creates the real `accounts_user` in a transaction, marks it verified, and consumes the pending registration. This endpoint does not issue JWT tokens; the user must log in after verification.
  - Errors keep `detail` and may include `code`: `PENDING_REGISTRATION_NOT_FOUND`, `VERIFY_CODE_INVALID`, `VERIFY_CODE_EXPIRED`, `VERIFY_TOO_MANY_ATTEMPTS`, `REGISTRATION_ALREADY_VERIFIED`, `EMAIL_ALREADY_REGISTERED`.
- `POST /verify-email/resend`
  - Public endpoint. Body: `{ "email": "..." }`.
  - Resends from `PendingRegistration`; it does not create `accounts_user`.
  - Success: `200` with `expires_in=600`, `resend_after=60`.
  - Cooldown: `429` with `code=RESEND_COOLDOWN`, `retry_after=<seconds>`.
  - Email send failure: `503` with `code=EMAIL_SEND_FAILED`.
- `POST /resend-verification`
  - Legacy alias for existing unverified users. New signups should use `/verify-email/resend`.

SMTP values must be supplied through local environment variables. Do not commit real SMTP credentials. For Gmail SMTP, use an app password, not the normal account password.
