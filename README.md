# Career_Dot_Zip
Final Project - 모의면접 시스템

## Email Verification API

Base path: `/api/v1/auth`

- `POST /signup`
  - Public endpoint. Creates an unverified account and sends a 6-digit verification code.
  - Success: `201` with `requires_verification=true`, `expires_in=600`, `resend_after=60`.
  - Verification email send failure: `503` with `code=EMAIL_SEND_FAILED`.
- `POST /verify-email`
  - Public endpoint. Body: `{ "email": "...", "code": "123456" }`.
  - Success: `200`. This endpoint does not issue JWT tokens; the user must log in after verification.
  - Errors keep `detail` and may include `code`: `VERIFY_CODE_INVALID`, `VERIFY_CODE_EXPIRED`, `VERIFY_TOO_MANY_ATTEMPTS`.
- `POST /resend-verification`
  - Public endpoint. Body: `{ "email": "..." }`.
  - Success: `200` with `expires_in=600`, `resend_after=60`.
  - Cooldown: `429` with `code=RESEND_COOLDOWN`, `retry_after=<seconds>`.
  - Email send failure: `503` with `code=EMAIL_SEND_FAILED`.

SMTP values must be supplied through local environment variables. Do not commit real SMTP credentials. For Gmail SMTP, use an app password, not the normal account password.
