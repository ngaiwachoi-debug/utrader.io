# Verify Dev Login and Gross Profit (68.93)

## 0. Ensure the correct backend is running (Gross Profit DB fallback)

The Gross Profit fix (DB fallback, `?source=db`, seed script) only works when the **backend process** is the one from this project. If you see **$0.00** in Profit Center:

1. **Check which backend is serving**  
   Open in the browser: `http://127.0.0.1:8000/api/version`  
   - If you see `{"version":"gross-profit-db-fallback","source_db_supported":true}` → this backend has the fix; proceed to seed/refresh.  
   - If you get connection refused or a different response → start the backend from this project (see §2) and ensure nothing else is using port 8000.

2. **Seed the snapshot** (so DB has a value to show after restart/cache miss):  
   From project root: `python scripts/seed_gross_profit_snapshot.py choiwangai@gmail.com 72.20`

3. **Restart the backend** from the **project root** (e.g. `python -m uvicorn main:app --host 127.0.0.1 --port 8000`) so it loads the code that reads the snapshot and supports `?source=db`.

4. Reload Profit Center; Gross Profit should show the persisted value (e.g. 72.20).

## 1. Backend env

In the same terminal (or `.env` in project root) where you start the API, set:

- `ALLOW_DEV_CONNECT=1`
- `NEXTAUTH_SECRET=<same as frontend NextAuth, e.g. from frontend/.env.local>`
- `REDIS_URL` (if your app uses Redis)
- `DATABASE_URL` (or rely on `database.py` fallback)

## 2. Start backend

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
$env:ALLOW_DEV_CONNECT="1"
$env:NEXTAUTH_SECRET="your-nextauth-secret"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

(Or use your existing `.env` and start command.)

## 3. Get dev token and refresh gross

In **another** terminal (PowerShell):

```powershell
# Replace with your API base if different
$base = "http://127.0.0.1:8000"

# 1) Dev login as choiwangai@gmail.com
$login = Invoke-RestMethod -Uri "$base/dev/login-as" -Method POST -ContentType "application/json" -Body '{"email":"choiwangai@gmail.com"}'
$token = $login.token
if (-not $token) { Write-Host "No token"; exit 1 }
Write-Host "Token received (first 20 chars): $($token.Substring(0, [Math]::Min(20, $token.Length)))..."

# 2) Force refresh lending stats (hits Bitfinex, updates snapshot)
$headers = @{ Authorization = "Bearer $token" }
$refresh = Invoke-RestMethod -Uri "$base/api/refresh-lending-stats" -Method POST -Headers $headers
Write-Host "Refresh gross_profit: $($refresh.gross_profit)"

# 3) User status (should show same gross with 2 decimals)
$status = Invoke-RestMethod -Uri "$base/user-status/2" -Headers $headers
Write-Host "user-status gross_profit_usd: $($status.gross_profit_usd)"
```

Expected: `gross_profit` and `gross_profit_usd` around **68.93** or **69.03** (2 decimals), depending on ledger data.

## 4. Login choiwangai bypassing Google, then check Gross Profit (2 decimals)

1. Start frontend: `cd frontend && npm run dev`
2. Open landing page: `http://localhost:3000` or `http://localhost:3000/en`
3. Click **"Dev: Login as choiwangai@gmail.com"** (no Google sign-in).
4. You are redirected to the dashboard.
5. Open **Profit Center**. **Gross Profit** must show **$68.93** (or **$69.03** from ledger sum) with **exactly 2 decimals** (e.g. `$68.93` or `$69.03`). The UI uses `.toFixed(2)` and the API returns `gross_profit` rounded to 2 decimals.

## 5. If Gross is wrong or stale

- Ensure choiwangai’s vault `created_at` is **2026-02-22 09:30** (UTC):
  ```powershell
  python scripts/set_choiwangai_registration.py
  ```
- Profit Center calls `POST /api/refresh-lending-stats` on load; that recomputes from Bitfinex ledgers (Margin Funding Payment) between `vault.created_at` and now. If the snapshot was from before you set `created_at`, one refresh after the script is enough.

## Fixes applied in code

- **main.py**
  - `FundingTradesResponse.calculation_breakdown` was using `CalculationBreakdown` before the class was defined; changed to forward reference `Optional["CalculationBreakdown"]` so the app starts.
  - **user-status 500**: If the `performance_logs` table is missing the `waroc` column (schema out of date), the endpoint no longer crashes; it catches `ProgrammingError` and returns utilization 0.
- **Gross 68.93**: Depends on (1) vault `created_at` = 2026-02-22 09:30 (run `scripts/set_choiwangai_registration.py`), (2) choiwangai’s Bitfinex keys being the same as in your script, (3) opening Profit Center or calling `POST /api/refresh-lending-stats` once so ledgers are fetched and the snapshot is updated.
- **Profit Center + dev login**: All fetches (`/stats/{userId}/lending`, `/stats/{userId}?start=&end=`, etc.) now send the Bearer token in `headers`, so when you use "Dev: Login as choiwangai", Profit Center gets data for that user and Gross Profit shows with 2 decimals.
