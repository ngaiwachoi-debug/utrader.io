# /user-status/2 Fix – Validation

## Network tab: "2" and "me" are your API calls

Chrome shows the **last path segment** as the request name. So:

- **"2"** = full URL `http://localhost:3000/api-backend/user-status/2` (this is the user-status request).
- **"me"** = `/api-backend/me` or `/api/me` (current user).

Click the row **"2"** → in the right panel, **Request URL** will show `.../api-backend/user-status/2`. That request is proxied to the backend at `127.0.0.1:8000/user-status/2`.

---

## 401 on "2" and "me": fix NEXTAUTH_SECRET

Backend returns 401 when the JWT from the frontend cannot be verified. Most often:

- **Backend and frontend must use the same `NEXTAUTH_SECRET`.**

Do this:

1. **One secret:** In the project root `.env` (or backend env), set `NEXTAUTH_SECRET=<same-value>`.
2. **Frontend:** Next.js reads `NEXTAUTH_SECRET` from `.env` or `.env.local` in the `frontend` folder (or root). Ensure it’s the same value.
3. **Backend:** Start the backend from the project root so it loads the same `.env`, e.g. `cd c:\Users\choiw\Desktop\bifinex\buildnew` then `python -m uvicorn main:app --host 127.0.0.1 --port 8000`. If you use a different env file for the backend, put the same `NEXTAUTH_SECRET` there.
4. Restart both frontend and backend after changing env.

---

## 1. Browser console (token fallback; force user-status/2 → 200)

Use the **same origin** so the request goes through the proxy (no CORS). Paste in DevTools → Console on `localhost:3000`:

```js
const token=(await(await fetch('/api/auth/token',{credentials:'include'})).json()).token||sessionStorage.getItem('utrader_dev_backend_token');const r=await fetch('/api-backend/user-status/2',{credentials:'include',headers:token?{Authorization:'Bearer '+token}:{}});console.log(r.status,await r.json())
```

Expect: `200` and body with `plan_tier: "whales"`.

---

## 2. Quick check list (3 steps)

1. **Network:** DevTools → Network, reload dashboard. Find the request named **"2"** (or filter by `user-status`). Open it → Request URL = `.../api-backend/user-status/2`. Confirm **Status 200** (after fixing NEXTAUTH_SECRET).
2. **Response:** For that request → Response tab → body contains `"plan_tier": "whales"`.
3. **UI:** Dashboard shows **Plan: whales** beside the header.
