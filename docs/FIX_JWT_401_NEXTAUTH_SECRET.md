# Fix JWT 401 (Mismatched NEXTAUTH_SECRET) + Validate /api-backend/user-status/2

**Why 401 happens:** The frontend signs the JWT with one secret; the backend verifies it with another. If they differ (or the backend has no secret), verification fails and the backend returns 401. Use the **same** `NEXTAUTH_SECRET` in both places.

**Exact secret (must match in both root `.env` and `frontend/.env.local`):**
```env
NEXTAUTH_SECRET="xqaJwgwFBGjekuoik674vN375pHj9EzHSpV9UAgoezk="
```

---

## 1. NEXTAUTH_SECRET sync (step-by-step)

### Option A: One-shot validate + sync (recommended)

From project root, run the script that verifies root `.env` and writes the **exact** secret to `frontend/.env.local`:

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
powershell -ExecutionPolicy Bypass -File scripts\validate_nextauth_secret.ps1
```

This checks that root `.env` exists and contains `NEXTAUTH_SECRET`, then creates/overwrites `frontend/.env.local` with the same value. Then restart backend and frontend (Section 2).

### Option B: Manual – use root `.env` secret in the frontend

1. Open the **root** `.env` (project root, same folder as `main.py`).
2. Copy the line: `NEXTAUTH_SECRET="xqaJwgwFBGjekuoik674vN375pHj9EzHSpV9UAgoezk="`.
3. Create or edit **frontend/.env.local** and paste that line. Save.

### Option C: Generate a new secret and set it in both places

Generate a secret (run once in a terminal):

**PowerShell:**

```powershell
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])
```

**Or Node (if you have Node):**

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
```

Copy the output (e.g. `K7x9mP2...`). Then:

1. **Backend:** Open **root** `.env`. Set or replace:
   ```
   NEXTAUTH_SECRET="PASTE_THE_GENERATED_VALUE_HERE"
   ```
   Save.

2. **Frontend:** Create or edit **frontend/.env.local**. Add or replace:
   ```
   NEXTAUTH_SECRET="PASTE_THE_SAME_VALUE_HERE"
   ```
   Save.

### Verify the secret is loaded

- **Check root .env (PowerShell):**  
  `Get-Content c:\Users\choiw\Desktop\bifinex\buildnew\.env | Select-String NEXTAUTH_SECRET`  
  Should show a line containing `NEXTAUTH_SECRET="xqaJwgwFBGjekuoik674vN375pHj9EzHSpV9UAgoezk="`.
- **Backend:** Start uvicorn from the **project root** so `load_dotenv()` (in `main.py`) loads root `.env`. Run `pip install -r requirements.txt` (includes `python-dotenv`), then from root: `python -m uvicorn main:app --host 127.0.0.1 --port 8000`.
- **Frontend:** Next.js loads `frontend/.env.local` when you run `npm run dev` from the frontend folder. After running the sync script or manually creating `.env.local`, restart the frontend and use the console snippet below to confirm 200.

---

## 2. Restart instructions (frontend + backend)

**Backend (FastAPI on 8000):**

1. In the terminal where uvicorn is running, press **Ctrl+C** to stop.
2. Run (from project root so root `.env` is loaded):
   ```powershell
   cd c:\Users\choiw\Desktop\bifinex\buildnew
   pip install -r requirements.txt
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
3. Leave it running.

**Frontend (Next.js on 3000):**

1. In the terminal where the dev server is running, press **Ctrl+C** to stop.
2. Run:
   ```powershell
   cd c:\Users\choiw\Desktop\bifinex\buildnew\frontend
   npm run dev -- -p 3000
   ```
3. Leave it running.

Open the app at **http://localhost:3000**. You **must re-login** (sign out, then sign in again) so the frontend issues a new JWT with the synced secret; otherwise the old token may still be used and verification can fail.

**Quick check that the frontend has the secret:** While logged in, open **http://localhost:3000/api/auth/token** in the browser. If you see `{"error":"NEXTAUTH_SECRET not set..."}` (500), run the sync script again and restart the frontend. If you see `{"token":null}` (401), you're not logged in. If you see `{"token":"eyJ..."}` (200), the secret is loaded.

---

## 3. Console validation snippet (same origin, no CORS)

Uses **/api-backend/user-status/2** (proxied to the backend). Paste in DevTools → Console while on **http://localhost:3000** (e.g. dashboard):

```js
const token=(await(await fetch('/api/auth/token',{credentials:'include'})).json()).token||sessionStorage.getItem('utrader_dev_backend_token');const r=await fetch('/api-backend/user-status/2',{credentials:'include',headers:token?{Authorization:'Bearer '+token}:{}});console.log(r.status,await r.json())
```

- **Expected:** `200` and an object including `plan_tier: "whales"`.
- If you see `401`, the secret is still mismatched or not loaded; re-check section 1 and restart both servers.

---

## 4. Network / UI validation checklist (3 steps)

1. **Network:** DevTools → Network, reload the dashboard. Find the request named **"2"** (or filter by `user-status`). Click it → Request URL = `http://localhost:3000/api-backend/user-status/2`. Confirm **Status 200**.
2. **Response:** With that request selected, open the **Response** tab. Body should include `"plan_tier": "whales"`.
3. **UI:** On the dashboard, next to the header you should see **Plan: whales** (from the UserStatusOnLoad component).

---

## 5. Troubleshooting (if 401 persists)

| Check | What to do |
|-------|------------|
| **Secret not loaded** | Run `scripts\validate_nextauth_secret.ps1` from project root to sync the exact secret to `frontend/.env.local`. Backend: start uvicorn from **project root**. Restart both. |
| **Proxy** | Request URL for "2" must be `http://localhost:3000/api-backend/user-status/2`. Backend on `127.0.0.1:8000`. |
| **JWT expired** | Log out and log in again (or use “Dev: Login as …” if you use that) to get a new token. Then rerun the console snippet. |
| **Frontend .env.local missing** | Create `frontend/.env.local` with: `NEXTAUTH_SECRET="xqaJwgwFBGjekuoik674vN375pHj9EzHSpV9UAgoezk="`. Restart frontend. |
| **Backend debug logs** | If `debug-1b4a77.log` exists: `secretLoaded: true` and `decodeOk: true` = success; `decodeOk: false` + `errorMsg` = secret mismatch. |
| **401 not from this backend** | In Network tab, open the 401 response → **Headers**. If **X-Backend-Log: 1b4a77** is missing, the response is from Next.js or an old backend. Stop all uvicorn processes, start only from project root: `cd c:\Users\choiw\Desktop\bifinex\buildnew` then `python -m uvicorn main:app --host 127.0.0.1 --port 8000`. |
| **401 with "column users.key_deletions does not exist"** | JWT is valid; the DB is missing a column. From project root run: `python migrations/run_reconciliation_key_deletions_migration.py`. Then restart the backend and try again. |
| **Quotes / spaces** | Use `NEXTAUTH_SECRET="xqaJwgwFBGjekuoik674vN375pHj9EzHSpV9UAgoezk="` with no spaces around `=`. |

After any change to `.env` or `.env.local`, **restart both** the backend and the frontend.
