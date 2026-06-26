# Current State Audit

Date: 2026-06-26

## Git Baseline

- Backend branch before work: `feature/evaluation-filler-count-fix`
- Working branch created for this work: `feature/integrated-enhancement-p0-p2`
- Recent commits:
  - `05cfe25 docs: 평가 수정 커밋에서 ERD 변경 제외`
  - `1b7a753 fix: 평가 filler count 계산 오류 수정`
  - `80cca55 chore: 최신 develop 변경 병합`
- Existing untracked files were present before this work and were not reset:
  - `artifacts/`
  - `docs/CAREER_ZIP_ENHANCEMENT_PLAN.md`
  - `docs/submission/`

## Backend

- Django apps include accounts, input, interview, evaluation, report, mypage, prompt, admin_api, external, question_bank, analysis.
- `PendingRegistration` already exists and signup creates pending data before User creation.
- `apps.external` already exposes `/api/v1/external/jobs` and `/api/v1/external/jobs/{job_id}`, but it was small JSON-sample based and used `source="MOCK"`.
- `JobDescription` has no dedicated source field. Existing `input_method` supports `TEXT`, `PDF`, `URL`, `OCR`.
- Report serializers expose `overall_score`, but no explicit `score_status`, `evaluation_status`, or `is_mock`.
- Admin API has dashboard/member/audit-log basics, but no point adjustment endpoints.
- Point fields and `PointHistory` do not exist yet.
- `django_apscheduler` was required unconditionally; local runtime lacked it.
- `.env` selects MySQL through `DATABASE_URL`; current local Python had `pymysql` but no `mysqlclient`.

## Frontend

- Frontend repo exists at `C:\SKN26\CAREER_DOT_ZIP_FRONTEND`.
- JD input page already supports manual input, PDF upload, and Mock job search/save.
- `jobsApi` calls `/external/jobs` and posts selected jobs to `/jds`.
- Login currently stores token and always navigates to `/mypage`; it does not check profile completion.
- Axios already has a single refresh promise to avoid concurrent refresh storms.
- Report adapter preserves null for category metrics, but overall/radar/question scores still coerce missing scores to 0 in some paths.

## Baseline Tests

- `python manage.py check` initially failed because `django_apscheduler` was not installed.
- After optionalizing `django_apscheduler` and adding a PyMySQL fallback, `python manage.py check` passed.
- `python manage.py makemigrations --check --dry-run` against `.env` MySQL was blocked by network/socket access to the configured Aiven host. Local SQLite verification will be used for migration shape; live MySQL is `ENV_REQUIRED`.
