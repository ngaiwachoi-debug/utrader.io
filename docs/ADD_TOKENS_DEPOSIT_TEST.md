# Add Tokens (USD Deposit) – Testing Instructions

The "Add tokens" form uses **1 USD = 10 tokens**, minimum **$1**. No Stripe payment is required to test validation and the success message.

---

## Step-by-step (no payment required)

### 1. Run the backend with dev auth

```powershell
# In backend directory; .env must have ALLOW_DEV_CONNECT=1 (and DATABASE_URL, etc.)
uvicorn main:app --reload
```

### 2. Log in as a test user

Create a user (if needed) and get a JWT:

```powershell
# Create user (optional; use an existing @gmail.com user if you have one)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/dev/create-test-user" -Method POST -ContentType "application/json" -Body '{"email":"test-addtokens@gmail.com"}'

# Get JWT
$login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/dev/login-as" -Method POST -ContentType "application/json" -Body '{"email":"test-addtokens@gmail.com"}'
$token = $login.token
```

### 3. Open the Subscription page in the app

- Open the frontend (e.g. `http://localhost:3000`), log in with the same user (or use the JWT in the frontend if it uses dev login).
- Go to **Dashboard → Subscription**.
- Find the **"Add tokens"** section (USD input + "Purchase tokens" button).

### 4. Enter $50 and submit

- In **Amount (USD)** enter `50`.
- Click **Purchase tokens** (or "購買代幣").
- You should see:
  - Loading: **"Calculating tokens..."**
  - Then success: **"500 tokens will be added after payment"**
- The input should clear after success.

### 5. Check backend logs

You should see a line like:

```
token_deposit_calculation user_id=... usd_amount=50.0 tokens_to_award=500
```

---

## Validation checks (optional)

- **$0.99** or **$0.5** → Error: **"Minimum deposit is $1"**
- **Empty or non-numeric** → Error: **"Please enter a valid USD amount"**
- **$10.99** → Success: **"109 tokens will be added after payment"** (10.99 × 10 → 109)

---

## Unit tests (no server needed)

From project root:

```powershell
python tests/test_token_deposits.py
```

Or with pytest:

```powershell
python -m pytest tests/test_token_deposits.py -v
```

Tests cover: $50→500, $10.99→109, $120.50→1205, reject $0.99, reject negative, reject non-numeric.
