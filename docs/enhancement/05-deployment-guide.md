# Deployment Guide

## Migration Order

1. Apply existing migrations through current heads.
2. Apply `admin_api.0004_restore_llm_usage_log` to restore the table used by `apps.analysis.services.utils`.
3. Apply `accounts.0006_points_ledger` to add user point fields and `accounts_point_history`.

## Mock Jobs

Default in-memory synthetic data:

```bash
python manage.py seed_mock_jobs --count 10000 --seed 2026 --dry-run
```

Optional local generated snapshot:

```bash
python manage.py seed_mock_jobs --count 10000 --seed 2026
```

The default generated file is `apps/external/data/mock_jobs.generated.json` and is ignored by Git.

## Environment Variables

- `JOBS_PROVIDER`: `mock` by default.
- `MOCK_JOBS_COUNT`: default `10000`.
- `MOCK_JOBS_SEED`: default `2026`.
- `MOCK_JOBS_DATA_FILE`: optional local generated JSON snapshot path.

## Runtime Notes

- `django_apscheduler` is optional at import time. If installed, it is included in `INSTALLED_APPS`; if missing, the API can still boot.
- MySQL uses `mysqlclient` when available and falls back to installed `pymysql` compatibility when needed.
- `/api/v1/health` returns only coarse `status` and `database` values and does not expose external provider details or secrets.

## Rollback Notes

- Do not delete point history rows manually. If rollback is required, export `accounts_point_history` first.
- Generated mock job snapshots are local artifacts and can be deleted without schema impact.
