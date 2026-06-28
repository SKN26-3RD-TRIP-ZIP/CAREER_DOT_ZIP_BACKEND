# ERD And Migration Plan

## Accounts

`accounts_user` gains:

- `point_balance` integer, default `0`
- `point_last_updated_at` datetime, nullable

New append-only model:

`accounts_point_history`

- `id`
- `user`
- `transaction_type`
- `amount`
- `balance_after`
- `reason_code`
- `reference_id`
- `idempotency_key`
- `policy_version`
- `description`
- `created_at`

Rules:

- Do not update or delete historical transactions.
- Balance updates and history creation run in one DB transaction.
- `select_for_update` protects concurrent balance changes.
- `idempotency_key` prevents duplicate point transactions when supplied.

## Mock Jobs

No DB migration is needed. Jobs are synthetic and deterministic. Large generated snapshots are local/ignored; the API can also generate from seed in memory.

## Reports

No DB migration is needed for score status. Status fields are derived from existing report summary metadata and response shape.

## Rollback Notes

- Accounts migration rollback removes the point balance columns and `PointHistory`; run only after confirming no production point ledger data needs retention.
- Mock job changes are stateless and can be rolled back with code.
- Optional dependency fallback changes in settings are non-schema changes.
