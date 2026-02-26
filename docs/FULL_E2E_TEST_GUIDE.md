# Full E2E Test Guide – Registration, Subscription UI, Add Tokens

End-to-end validation of **registration tokens**, **subscription page (monthly/yearly)**, and **custom deposit form** using a single fake test user. No Stripe payment required.

---

## 1. Prerequisites

| Requirement | How to confirm |
|-------------|----------------|
| **Backend running (dev mode)** | Backend started (e.g. `uvicorn main:app --reload`). In `.env`: `ALLOW_DEV_CONNECT=1`. |
| **Frontend running** | Frontend started (e.g. `npm run dev` in `frontend/`). Default: `http://localhost:3000`. |
| **Database** | PostgreSQL reachable; `DATABASE_URL` in backend `.env`. |

**Tools needed:**

- **Browser** – Chrome/Edge/Firefox (for UI + DevTools → Network).
- **Terminal** – PowerShell (Windows) or Bash (Linux/macOS/WSL) for API commands.
- **PostgreSQL client** (optional) – `psql`, DBeaver, or any client to run validation/cleanup SQL.

---

## 2. Step 1: Create a Fake Test User (E2E Registration Tokens)

Test user email must end with `@gmail.com` (backend rule). Use: **`e2e-test-all@gmail.com`**.

### API: Create the test user

**PowerShell:**

```powershell
$body = '{"email":"e2e-test-all@gmail.com"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/dev/create-test-user" -Method POST -ContentType "application/json" -Body $body
```

**curl (Bash/WSL):**

```bash
curl -s -X POST http://127.0.0.1:8000/dev/create-test-user \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e-test-all@gmail.com"}'
```

**Expected response:** `{ "user_id": <number>, "email": "e2e-test-all@gmail.com" }`. Note `user_id` for cleanup.

### DB: Confirm registration tokens

Run in your PostgreSQL client (replace `USER_ID` with the `user_id` from above, or use the email):

```sql
SELECT u.id, u.email, u.plan_tier,
       b.tokens_remaining, b.purchased_tokens
FROM users u
LEFT JOIN user_token_balance b ON b.user_id = u.id
WHERE u.email = 'e2e-test-all@gmail.com';
```

**Expected:**

| id   | email                | plan_tier | tokens_remaining | purchased_tokens |
|------|----------------------|-----------|------------------|------------------|
| &lt;id&gt; | e2e-test-all@gmail.com | trial     | 150              | 50               |

- **Registration tokens:** `tokens_remaining = 150`, `purchased_tokens = 50` (50 is the bonus so API shows 150).

### UI: Log in as this test user

1. **Get a JWT** (backend only knows email; frontend may use Google or dev login):
   - **PowerShell:**  
     `$login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/dev/login-as" -Method POST -ContentType "application/json" -Body '{"email":"e2e-test-all@gmail.com"}'; $login.token`
   - **curl:**  
     `curl -s -X POST http://127.0.0.1:8000/dev/login-as -H "Content-Type: application/json" -d '{"email":"e2e-test-all@gmail.com"}'`
2. If your frontend has a **dev login** (e.g. email input that calls `/dev/login-as`), enter **`e2e-test-all@gmail.com`** and log in.
3. If the frontend only supports Google OAuth, use the same email only if that Google account exists; otherwise treat “log in as test user” as “use JWT for API checks” and do the rest of the test via API/script.

---

## 3. Step 2: Test Subscription UI (Monthly/Yearly Buttons)

### UI actions

1. In the app, go to **Dashboard → Subscription** (or the route that shows the Subscription page).
2. **Check plan cards and buttons:**
   - **Pro:**  
     - “Subscribe to Pro (Monthly)” (or equivalent).  
     - “$192/year Save 10%” (or equivalent).
   - **AI Ultra:**  
     - “Subscribe to AI Ultra (Monthly)”.  
     - “$576/year Save 10%”.
   - **Whales AI:**  
     - “Subscribe to Whales AI (Monthly)”.  
     - “$1920/year Save 10%”.
3. **Token display:** Pro plan should show **“2000 token credit”** (or “2000 tokens”) to match the monthly award.
4. **Click “Subscribe to Pro (Monthly)”:**
   - Button should show a **loading state** (spinner; button text may stay “Subscribe to Pro (Monthly)” or show a loading indicator—optional: you can add “Processing Pro Monthly...” in the UI later).
   - No crash; either redirect to Stripe (if configured) or an error message (if Stripe is not configured).

### Network check (DevTools)

1. Open **DevTools → Network**.
2. Click **“Subscribe to Pro (Monthly)”** again.
3. Find the request to **`/api/create-checkout-session`** (or your API base + that path).
4. **Request:** Method POST, body: `{ "plan": "pro", "interval": "monthly" }`.
5. **Response:**
   - **If Stripe is configured:** `200 OK`, body has `url` (Stripe Checkout).
   - **If Stripe is not configured:** `503` with message like “Subscription is not configured…” (acceptable for this E2E; see “Acceptable pending errors” below).

### Expected vs acceptable

- **Expected:** API is called with `plan` and `interval`, and the backend responds (200 or 503).
- **Acceptable:** 503 “Stripe price ID / env missing” when Stripe is not set up; no need to complete payment.

---

## 4. Step 3: Test Custom Deposit Form (Add Tokens)

### Invalid inputs (validation)

On the Subscription page, find the **“Add tokens”** form (USD amount + submit button).

| Action        | Expected result                                      |
|---------------|------------------------------------------------------|
| Enter **0.99** → Submit | Error: **“Minimum deposit is $1”**                  |
| Enter **abc** → Submit  | Error: **“Please enter a valid USD amount”**        |
| Enter **-50** → Submit  | Error: **“Minimum deposit is $1”** (or similar)     |

### Valid input: $50

1. Enter **50** in the USD field.
2. **Preview:** Text like **“You get 500 tokens”** (50 × 10).
3. Click the submit button (e.g. “Purchase tokens”):
   - **Loading:** “Calculating tokens...” (or spinner).
   - **Success:** “500 tokens will be added after payment”.
   - Input clears after success.

### Network check (DevTools)

1. **DevTools → Network** (and clear if you like).
2. Submit **$50** again.
3. Find **`/api/v1/tokens/deposit`**:
   - **Request:** POST, body `{ "usd_amount": 50 }` (or 50.0).
   - **Response:** **200 OK**, body e.g.  
     `{ "status": "success", "usd_amount": 50, "tokens_to_award": 500, "message": "..." }`.

### Backend log

In the backend terminal, you should see something like:

```
token_deposit_calculation user_id=<ID> usd_amount=50.0 tokens_to_award=500
```

(Replace `<ID>` with the test user’s `user_id`.)

### DB after deposit (no Stripe)

- **Expected:** `user_token_balance` is **unchanged** (no tokens added yet), because no Stripe payment was made. Only the calculation and success message are tested.

---

## 5. Step 4: Cleanup

### Delete test user and token row

Run in PostgreSQL (replace `USER_ID` with the `user_id` from Step 1, or use the email subquery):

```sql
-- Replace USER_ID with the actual id, or use the SELECT below to get it
DELETE FROM user_token_balance WHERE user_id = (SELECT id FROM users WHERE email = 'e2e-test-all@gmail.com');
DELETE FROM users WHERE email = 'e2e-test-all@gmail.com';
```

If you have other tables that reference `users.id` (e.g. `api_vault`), delete or update those first as needed.

### Log out in the UI

- Use the app’s logout/sign-out so the session is cleared.

---

## 6. Summary Table: Expected vs Actual

Use this to tick off results as you run the E2E.

| Step | What to check | Expected result | Actual (fill in) |
|------|----------------|-----------------|-------------------|
| **1. Create user** | API response | `user_id`, `email` returned | |
| **1. DB** | `users` + `user_token_balance` | User exists; `tokens_remaining=150`, `purchased_tokens=50` | |
| **2. Subscription UI** | Buttons visible | Pro/AI Ultra/Whales monthly + yearly ($192, $576, $1920) | |
| **2. Pro tokens** | Pro plan copy | Shows “2000” tokens | |
| **2. Click Pro Monthly** | Loading + API call | Spinner; POST `/api/create-checkout-session` with `plan`, `interval` | |
| **2. API response** | Status | 200 (Stripe configured) or 503 (Stripe not configured) | |
| **3. Deposit $0.99** | Error message | “Minimum deposit is $1” | |
| **3. Deposit “abc”** | Error message | “Please enter a valid USD amount” | |
| **3. Deposit -50** | Error message | “Minimum deposit is $1” (or validation error) | |
| **3. Deposit $50** | Preview | “You get 500 tokens” | |
| **3. Deposit $50 submit** | Loading then success | “Calculating tokens...” then “500 tokens will be added after payment” | |
| **3. Deposit API** | Network | POST `/api/v1/tokens/deposit` body `usd_amount: 50`, response 200 | |
| **3. Backend log** | Log line | `token_deposit_calculation user_id=... usd_amount=50.0 tokens_to_award=500` | |
| **3. DB after deposit** | `user_token_balance` | Unchanged (no payment yet) | |
| **4. Cleanup** | SQL + logout | User and token row deleted; logged out | |

---

## 7. Acceptable “Pending” Errors

- **503 from `/api/create-checkout-session`** with “Subscription is not configured. Please set STRIPE_API_KEY and Stripe Price IDs…”  
  → Expected when Stripe env vars are not set. No payment required for this E2E.
- **Browser alert/error** after clicking a subscription button when Stripe is missing  
  → Expected; the E2E only verifies that the API is called and the backend responds (200 or 503).

---

## 8. Automated API-Only Run (Script)

For a **quick API-only** check (no UI, no DB), ensure the **backend is running** with `ALLOW_DEV_CONNECT=1`, then run:

- **PowerShell (Windows):**  
  `.\scripts\test_all_features_e2e.ps1`
- **Bash (Linux/macOS/WSL):**  
  `chmod +x scripts/test_all_features_e2e.sh` (once), then  
  `./scripts/test_all_features_e2e.sh`

The script will:

1. Create the test user (`e2e-test-all@gmail.com`).
2. Get a JWT via `/dev/login-as`.
3. Call `POST /api/create-checkout-session` (Pro monthly) and assert 200 or 503.
4. Call `POST /api/v1/tokens/deposit` with `usd_amount: 50` and assert 200 and `tokens_to_award: 500`.
5. Print cleanup SQL (you run it manually in your DB client).

No Stripe payment and no DB access required for the script; DB validation and full UI flow remain manual as in Steps 1–4 above.

---

## 9. Fully Automated E2E (Playwright + DB)

A **single Python script** runs all steps (pre-checks, create user, DB validation, UI login, subscription buttons, add-tokens form, DB check, cleanup) with **no manual UI or SQL**.

**Setup:**

1. Install dependencies:  
   `pip install -r scripts/requirements_e2e.txt`
2. Install Playwright browser:  
   `playwright install chrome`
3. Set DB credentials (one of):
   - `DATABASE_URL` (e.g. `postgresql://user:pass@host/dbname?sslmode=require`), or
   - `DB_HOST`, `DB_USER`, `DB_PASSWORD` (or `DB_PASS`), `DB_NAME` (optional: `DB_PORT`)
4. Backend running with `ALLOW_DEV_CONNECT=1`; frontend running (e.g. `npm run dev`).

**Run:**

```bash
python scripts/automated_e2e_test.py
```

**Optional env:**

- `E2E_API_BASE` — default `http://127.0.0.1:8000`
- `E2E_FRONTEND_BASE` — default `http://localhost:3000`
- `E2E_HEADLESS=0` — show browser window

**Output:** Pass/Fail per step in the console. On failure, screenshots are saved under `tests/screenshots/`. The script deletes the test user and token row automatically (no manual SQL).
