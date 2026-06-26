# Execution Plan

## P0

- Preserve actual score `0`; do not coerce missing scores to zero in report response contracts.
- Add explicit report score/evaluation status fields.
- Add profile-aware login redirect metadata.
- Keep PendingRegistration flow intact and validate through existing tests.

## Mock Jobs

- Expand current `apps.external` implementation instead of creating a duplicate app.
- Generate deterministic synthetic jobs from seed.
- Support requested query parameter names while keeping legacy frontend aliases.
- Add `is_mock=true` and `source=CAREER_ZIP_MOCK`.
- Add a management command compatible with `python manage.py seed_mock_jobs --count 10000 --seed 2026`.
- Add backend JD save endpoint for selected synthetic jobs.

## Points

- Add `point_balance` and `point_last_updated_at` to `accounts_user`.
- Add append-only `PointHistory`.
- Add point service with earn/use/refund/admin adjustment primitives.
- Add user and admin APIs with tests.

## Frontend

- Update login to use backend `next_path`.
- Update jobs API to use backend save endpoint and display unambiguous synthetic/mock wording.
- Preserve direct input/PDF fallback when Mock API fails.

## Verification

- Run Django check and targeted tests.
- Run migration dry-run with local SQLite when live MySQL is inaccessible.
- Run frontend build if the current environment permits it.
