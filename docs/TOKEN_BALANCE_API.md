# Token Balance API (v1)

Production-ready endpoint for real-time token balance, integrated with authentication, daily token deduction, and the existing database.

---

## Endpoint

**`GET /api/v1/users/me/token-balance`**

Returns the current user's token balance from `user_token_balance`. No new tables or columns; read-only. Values reflect state after the 10:15 UTC daily deduction.

---

## Authentication

- **Required**: JWT in `Authorization: Bearer <token>`.
- **Same pattern** as `/start-bot`, `/stop-bot`, `/bot-stats`: uses `get_current_user` dependency.
- **No token or invalid token**: `401 Unauthorized` with `{"detail": "Not authenticated"}`.

---

## Response schema (200 OK)

```json
{
  "tokens_remaining": 1500,
  "purchased_tokens": 2000,
  "last_gross_usd_used": 500.0,
  "updated_at": "2026-02-28T10:15:00Z"
}
```

| Field               | Type    | Description |
|---------------------|---------|-------------|
| `tokens_remaining`  | float   | Current balance after daily deduction. |
| `purchased_tokens`  | float   | Total tokens bought / subscribed. |
| `last_gross_usd_used` | float | Daily gross value used in the last deduction. |
| `updated_at`        | string \| null | UTC ISO 8601; `null` if row never updated. |

---

## Edge case: no `user_token_balance` row

If the user has no row in `user_token_balance`:

```json
{
  "tokens_remaining": 0,
  "purchased_tokens": 0,
  "last_gross_usd_used": 0.0,
  "updated_at": null
}
```

No error; safe defaults.

---

## Rate limiting

- **Limit**: 10 requests per minute per user (in-memory).
- **Exceeded**: `429 Too Many Requests` with `{"detail": "Rate limit exceeded: 10 requests per minute"}`.

---

## Error codes

| Code | Condition        | Body |
|------|------------------|------|
| 401  | Not authenticated | `{"detail": "Not authenticated"}` |
| 429  | Rate limit exceeded | `{"detail": "Rate limit exceeded: 10 requests per minute"}` |
| 500  | Internal error    | `{"detail": "Internal error retrieving token balance."}` (stack trace logged server-side only) |

---

## Compatibility

- **Bot lifecycle**: Does not call start/stop or ARQ; read-only. No impact on bot.
- **Daily profit snapshot (09:40 UTC)**: Writes `user_profit_snapshot` and related token updates; this endpoint only reads `user_token_balance`.
- **Daily token deduction (10:15 UTC)**: Updates `user_token_balance`; this endpoint returns the updated values after the next request.
- **Existing APIs**: No changes to `/user-token-balance/{user_id}` or other routes.
- **Frontend**: Can poll this endpoint (e.g. every 5–10s) for real-time balance; respect 429 and back off.

---

## How to get a valid JWT for testing

1. **Dev login** (requires `ALLOW_DEV_CONNECT=1` and `NEXTAUTH_SECRET`):
   ```bash
   curl -X POST http://127.0.0.1:8000/dev/login-as \
     -H "Content-Type: application/json" \
     -d '{"email":"your@email.com"}'
   ```
   Response: `{"token":"<JWT>"}`. Use that as `Bearer <JWT>`.

2. **NextAuth**: Use the token your frontend receives after login (e.g. from `/api/auth/token` or your auth provider).

---

## Example requests

**curl**
```bash
export TOKEN="<your-jwt>"
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/users/me/token-balance
```

**PowerShell**
```powershell
$token = "<your-jwt>"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/users/me/token-balance" -Headers @{ Authorization = "Bearer $token" }
```

---

## Verifying value after deduction

1. Note current `tokens_remaining` from `GET /api/v1/users/me/token-balance`.
2. Run daily deduction (dev): `curl -X POST http://127.0.0.1:8000/dev/run-daily-deduction` (with `ALLOW_DEV_CONNECT=1`; this runs for all users with positive `daily_gross_profit_usd`).
3. Call `GET /api/v1/users/me/token-balance` again; `tokens_remaining` and `last_gross_usd_used` should reflect the deduction (and `updated_at` if the row was updated).

---

## Unit tests

From project root (requires migrations applied, e.g. `users.bot_status`, `user_profit_snapshot.daily_gross_*`):

```bash
python -m pytest tests/test_token_balance_endpoint.py -v
# or
python tests/test_token_balance_endpoint.py
```

Tests cover: authenticated balance, 401 without auth, 429 when rate limit exceeded, defaults when no token row, and correct balance after `run_daily_token_deduction`.
