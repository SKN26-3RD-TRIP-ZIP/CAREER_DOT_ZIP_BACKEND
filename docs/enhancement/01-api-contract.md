# API Contract

## Mock Jobs

### `GET /api/v1/external/jobs`

Auth: Bearer token required.

Query parameters:

- `keyword` or legacy `q`
- `position`
- `career_type`
- `employment_type`
- `location` or legacy `region`
- `tech_stack` or legacy `tech`
- `page`
- `size`
- `ordering` or legacy `sort`

Response:

```json
{
  "source": "CAREER_ZIP_MOCK",
  "is_mock": true,
  "total": 10000,
  "page": 1,
  "size": 20,
  "results": []
}
```

### `GET /api/v1/external/jobs/{job_id}`

Auth: Bearer token required.

Returns one synthetic job with `source="CAREER_ZIP_MOCK"` and `is_mock=true`, or `404`.

### `POST /api/v1/external/jobs/{job_id}/save-jd`

Auth: Bearer token required.

Creates a user-owned `JobDescription` from the selected synthetic job using the existing JD model. No new JD source column is introduced; the generated JD text includes an explicit `CAREER_ZIP_MOCK` source marker.

## Points

### `GET /api/v1/users/me/points`

Auth: Bearer token required.

Returns current point balance and latest update timestamp.

### `GET /api/v1/users/me/points/history`

Auth: Bearer token required.

Query parameters: `page`, `size`.

Returns paginated append-only point transactions.

### `POST /api/v1/admin/members/{member_id}/points/adjust`

Admin auth required.

Request:

```json
{
  "amount": 100,
  "reason": "manual correction",
  "idempotency_key": "optional"
}
```

### `GET /api/v1/admin/points/history`

Admin auth required. Supports `page`, `size`, and optional `user_id`.

## Auth Me Redirect Metadata

`GET /api/v1/auth/me` now includes:

- `profile.exists`
- `profile.is_complete`
- `next_path`: `/admin/dashboard`, `/profile`, or `/mypage`

## Reports

Report serializers include:

- `score_status`: `SCORED`, `NOT_EVALUATED`, or `MOCK`
- `evaluation_status`: `COMPLETED`, `PENDING`, `FAILED`, or `MOCK`
- `is_mock`
