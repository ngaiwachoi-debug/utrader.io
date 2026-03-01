# Fix 500 Errors – Manual Steps & Validation

## MANUAL STEP 1: Run migration (if not already done)

Open PowerShell, then run **each line** (or run as one block):

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
python migrations/run_reconciliation_key_deletions_migration.py
```

Expected output:
- `PostgreSQL: user_profit_snapshot.reconciliation_completed added or already exists.`
- `PostgreSQL: users.key_deletions added or already exists.`

---

## MANUAL STEP 2: Restart backend

1. In the terminal where uvicorn is running, press **Ctrl+C** to stop.
2. Run:

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

3. Leave it running.

---

## MANUAL STEP 3: Restart frontend

1. In the terminal where the Next.js dev server is running, press **Ctrl+C** to stop.
2. Run:

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew\frontend
npm run dev -- -p 3000
```

3. Leave it running.

---

## Validation (browser)

1. Open **http://localhost:3000** and sign in if needed.
2. Open **DevTools** (F12) → **Console**.
3. Paste and run this snippet (same-origin `/api-backend`). It logs **each endpoint as it completes** so you see results even if one request is slow:

```js
(async () => {
  const token = (await (await fetch('/api/auth/token', { credentials: 'include' })).json()).token || sessionStorage.getItem('utrader_dev_backend_token');
  const opts = { credentials: 'include', ...(token ? { headers: { Authorization: 'Bearer ' + token } } : {}) };
  const urls = ['/user-status/2', '/wallets/2', '/stats/2/lending', '/stats/2/history?start=2026-01-25&end=2026-02-24'];
  for (const u of urls) {
    try {
      const r = await fetch('/api-backend' + u, opts);
      const d = await r.json().catch(() => ({}));
      console.log(u, r.status, d);
    } catch (e) {
      console.log(u, 'error', e.message);
    }
  }
  console.log('Done');
})();
```

**Expected:**
- Each line logs the **URL**, **status (200)**, and **response body**.
- `/user-status/2` body includes `plan_tier: "whales"` (or your current tier).
- Last line is `Done`. If a request hangs, the lines after it won’t appear until it finishes (or you can check the **Network** tab for that request’s status).

---

## If 500s persist

1. Run **Step 1** again, then **Step 2** (restart backend).
2. **Sign out and sign in** to get a new JWT.
3. Run the validation snippet again and note which URL still returns 500.
