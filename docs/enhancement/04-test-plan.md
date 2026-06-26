# Test Plan

## Executed

- `python manage.py check`
  - Initial result: failed because optional `django_apscheduler` was not installed.
  - After settings fallback: PASS.
- `DATABASE_URL=sqlite:///db.sqlite3 python manage.py makemigrations --check --dry-run`
  - PASS, no changes detected after generated migrations.
- `DATABASE_URL=sqlite:///db.sqlite3 python manage.py test apps.external.tests_mock_jobs apps.accounts.tests.test_points apps.accounts.tests.test_me apps.report.test_score_status apps.admin_api.test_points_admin`
  - PASS: 26 tests.
- `DATABASE_URL=sqlite:///db.sqlite3 python manage.py seed_mock_jobs --count 10000 --seed 2026 --dry-run`
  - PASS: generated 10,000 synthetic jobs in memory.
- `npm.cmd run build`
  - PASS after running with filesystem access to the frontend repo.

## Blocked Or Existing Issues

- Plain `python manage.py test` fails during test discovery before running tests because both `apps/analysis/tests.py` and `apps/analysis/tests/` exist. This is an existing test layout conflict and should be fixed separately.
- Live MySQL migration-history validation is `ENV_REQUIRED` in this sandbox because the configured Aiven host is blocked by socket/network permissions.

## Added/Updated Coverage

- Mock job seed reproducibility, 10,000 generation, aliases, filters, pagination, ordering, detail 404, and JD save ownership.
- Point ledger earn/use/refund, insufficient balance, idempotency, user APIs, and admin adjustment APIs.
- `auth/me` profile-aware next-path metadata.
- Final report score status for real 0, null, failed, and mock reports.
