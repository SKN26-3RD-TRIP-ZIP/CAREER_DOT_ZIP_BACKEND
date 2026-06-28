# Release Notes

## Added

- Deterministic `CAREER_ZIP_MOCK` synthetic job provider with 10,000-job generation support.
- `seed_mock_jobs` management command.
- `POST /api/v1/external/jobs/{job_id}/save-jd` for saving a synthetic job as the current user's JD.
- User point balance fields and append-only `PointHistory` ledger.
- User point APIs and admin point adjustment/history APIs.
- `GET /api/v1/health`.
- `auth/me` profile-aware `next_path` metadata.
- Report response fields: `score_status`, `evaluation_status`, `is_mock`.

## Changed

- Mock job list/detail responses now return `source="CAREER_ZIP_MOCK"` and `is_mock=true`.
- Mock job list accepts both new query names and legacy aliases.
- Frontend login now follows `auth/me.next_path`.
- Frontend JD input labels synthetic jobs clearly and saves through the backend save-JD endpoint.
- Frontend report adapter preserves missing overall scores as `null` instead of coercing them to `0`.
- Frontend growth chart excludes mock reports.

## Environment Required

- Live SMTP, OpenAI, OAuth, AWS, and remote MySQL validation require real credentials/network access and were not reported as successful in this local sandbox.
