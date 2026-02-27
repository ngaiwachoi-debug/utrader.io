# Gross Profit $0.00 – Fix Summary

## Root cause (from debug logs)

- The API always returns `gross_profit: 0` and never returns `db_snapshot_gross`.
- The verification script cannot reach `http://127.0.0.1:8000/api/version`.

So the process serving your requests is **not** the backend from this project (or no backend is running on 8000). The Gross Profit fix only works when that backend is running and the frontend calls it.

## Fix (do in order)

### 1. Start the backend from this project

In a terminal:

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Leave it running. You should see something like `Uvicorn running on http://127.0.0.1:8000`.

### 2. Seed the DB (if not done yet)

In **another** terminal, from the same project root:

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
python scripts/seed_gross_profit_snapshot.py choiwangai@gmail.com 72.20
```

You should see: `Updated user_profit_snapshot for choiwangai@gmail.com (user_id=2): gross_profit_usd=72.2` (or "Inserted...").

### 3. Point the frontend at this backend

- If you use `.env`: set `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000` (or leave it unset; default is 127.0.0.1:8000).
- Restart the Next.js dev server after changing env so it picks up the value.

### 4. Verify

In a browser open: `http://127.0.0.1:8000/api/version`  
You should see: `{"version":"gross-profit-db-fallback","source_db_supported":true}`.

Then open: `http://127.0.0.1:8000/stats/2/lending?source=db`  
You should see JSON with `gross_profit: 72.2` and `db_snapshot_gross: 72.2`.

### 5. Reload Profit Center

Open the dashboard as the test user and go to Profit Center. Gross Profit should show **72.20**.

## Optional: run the verify script

With the backend **already running**:

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
.\scripts\verify_gross_profit_backend.ps1
```

Both steps should report OK. If step 1 fails, the backend is not running on 8000. If step 2 reports gross_profit = 0, run the seed script (step 2 above) and run the verify script again.
