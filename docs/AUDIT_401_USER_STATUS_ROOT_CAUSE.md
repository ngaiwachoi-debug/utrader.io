# Audit: 401 Unauthorized on /user-status/2 (choiwangai@gmail.com)

## Root Cause Identification (Ranked by Probability)

### 1. **CORS: Frontend origin not allowed when using port 3003** (HIGH)

- **Location:** `main.py` lines 940–944 (`_cors_origins`).
- **Evidence:** `_cors_origins` only lists `3000`:
  - `http://127.0.0.1:3000`
  - `http://localhost:3000`
  - `http://0.0.0.0:3000`
  - **Missing:** `http://localhost:3003`, `http://127.0.0.1:3003`
- **Why it breaks auth:** When the app runs on **localhost:3003** (e.g. because 3000 was occupied), the browser sends `Origin: http://localhost:3003`. The backend does not list this origin, so it does not echo it in `Access-Control-Allow-Origin`. With `allow_credentials=True`, the browser may block the response or treat the request as non-credentialed; in some cases the request is sent but the client sees a failed request or the server’s 401 is the only visible result. Either way, the effective outcome is “401” or request failure when using 3003.
- **No change to auth logic:** Auth (JWT, `get_current_user`) is unchanged; the failure is due to origin/port not being allowed by CORS.

### 2. **Missing or invalid token (getBackendToken returns null or expired JWT)** (MEDIUM)

- **Location:** Frontend `lib/auth.ts` (`getBackendToken`), `app/api/auth/token/route.ts` (NextAuth JWT).
- **Flow:** `getBackendToken()` calls `fetch("/api/auth/token", { credentials: "include" })`. If that returns non-ok or no `token`, header is `{}` and no `Authorization` is sent → backend returns 401.
- **Why it could break:** If the user was on **3003** and CORS blocked the **backend** response from being read, the frontend might still call `/api/auth/token` (same origin, so no CORS issue). So token could be present. If, however, the **backend** request from 3003 was blocked or not sent as intended (e.g. preflight/credentials behavior), the visible symptom could still be 401 on `/user-status/2`. After fixing CORS, if 401 persists then token is missing or invalid (e.g. session expired, wrong NEXTAUTH_SECRET, or cookie not sent for some reason).
- **No recent code change** to `get_current_user` or JWT validation that would explain a new 401 by itself.

### 3. **Trace ID / context corruption** (LOW – rejected)

- **Location:** `utils/logging.py` (contextvars: `set_trace_id`, `get_trace_id`), used in schedulers and logging.
- **Conclusion:** Trace ID is stored in **contextvars** and used only for **logging**. It is not read from or written to the request; it does not touch `Authorization` or any header. Request handling and `get_current_user(Authorization=...)` are unchanged. **Rejected** as cause of 401.

---

## Fix Recommendations

### Fix 1: Add port 3003 (and common variants) to CORS (do this first)

**File:** `main.py`

Add origins for port 3003 so that when the frontend runs on 3003 (e.g. when 3000 is in use), the backend allows the request and the browser does not block the response.

**Edit:** Extend `_cors_origins` to include 3003 (and keep 3000):

```python
_cors_origins = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://0.0.0.0:3000",
    "http://127.0.0.1:3003",
    "http://localhost:3003",
]
```

- No change to late fee, reconciliation, Redis fallback, or trace ID logic.
- Backward compatible; only adds allowed origins.

### Fix 2: Optional – allow CORS via env (already supported)

If you already set `CORS_ORIGINS` in `.env` (e.g. `CORS_ORIGINS=http://localhost:3003,http://127.0.0.1:3003`), that would also allow 3003. The code change above makes 3003 allowed by default so local dev works even when the app falls back to 3003.

### Fix 3: If 401 persists after CORS – verify token path

1. In browser (on the page that calls `/user-status/2`): open DevTools → Application → Cookies and confirm NextAuth/session cookies are present for the current origin (e.g. localhost:3000 or 3003).
2. In DevTools → Network: trigger the request to `/user-status/2` and confirm the **Request Headers** include `Authorization: Bearer <token>`. If not, `getBackendToken()` is returning null (e.g. `/api/auth/token` failed or returned 401).
3. Backend: ensure `NEXTAUTH_SECRET` matches the frontend `.env` so JWT validation succeeds.

---

## Validation Steps

1. **Apply Fix 1** (add 3003 to `_cors_origins` in `main.py`).
2. **Restart backend** (uvicorn) so the new CORS list is loaded.
3. **Open app** at `http://localhost:3000` (or `http://localhost:3003` if that’s what you use).
4. **Log in** as choiwangai@gmail.com (or ensure existing session is valid).
5. **Trigger** a request to `/user-status/2` (e.g. load the dashboard/settings that call it).
6. **Check:**
   - DevTools → Network: request to `http://127.0.0.1:8000/user-status/2` → **200 OK** (not 401).
   - Response body includes `plan_tier` (e.g. `whales` for this user).
7. **Optional:** From browser console:
   ```js
   const t = await (await fetch('/api/auth/token', { credentials: 'include' })).json();
   const r = await fetch('http://127.0.0.1:8000/user-status/2', { headers: { Authorization: `Bearer ${t.token}` }, credentials: 'include' });
   console.log(r.status, await r.json());
   ```
   Expect `200` and the user-status object.

---

## Preventive Measures

1. **CORS and port usage:** When adding or changing frontend dev ports (e.g. 3003, 3001), add them to `_cors_origins` in `main.py` (or to `CORS_ORIGINS` in env) so backend always allows the current dev origin.
2. **Auth isolation:** Keep `get_current_user` and JWT logic in one place; avoid middleware or contextvars that touch the request or headers so auth cannot be accidentally bypassed or corrupted.
3. **Pre-deploy check:** Before release, test with the same origin/port as production (and, if applicable, with the fallback port used in dev) and confirm `/user-status/{id}` returns 200 for the logged-in user.
4. **No revert of date-range removal:** The removal of the date range button in `header.tsx` is UI-only and does not affect auth; no need to revert it.

---

## Summary

- **Most likely cause of 401** when using the app on **localhost:3003** is **CORS**: the backend did not allow origin `http://localhost:3003`, so the browser blocked or restricted the response; the visible result is 401 or failed request.
- **Fix:** Add `http://127.0.0.1:3003` and `http://localhost:3003` to `_cors_origins` in `main.py` and restart the backend.
- **If 401 remains:** Treat as token missing or invalid (check cookie, `Authorization` header, and `NEXTAUTH_SECRET`), using the validation steps above.
