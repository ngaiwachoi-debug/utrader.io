# Token Deduction Log Analysis for choiwangai@gmail.com

## 1. Location of Token Deduction Logic and Logs

### 1.1 Where deduction and gross profit are calculated

| Component | File / Location | Purpose |
|-----------|------------------|--------|
| **Daily token deduction (10:15 UTC)** | `services/daily_token_deduction.py` | Reads `daily_gross_profit_usd` from `user_profit_snapshot`, deducts 1:1 (USD = tokens deducted), updates `user_token_balance`. |
| **Gross profit from Bitfinex (09:40 UTC)** | `main.py` ~L169–250 | Calls `_refresh_user_lending_snapshot` per user; uses **Margin Funding Payment** from Bitfinex ledgers API; writes `gross_profit_usd` and `daily_gross_profit_usd` to `user_profit_snapshot`. |
| **Margin Funding Payment parsing** | `main.py` ~L1949–1990 | `_gross_and_fees_from_ledger_entries`: sums positive ledger amounts where `entry[8]` contains `"Margin Funding Payment"`. |
| **used_tokens / tokens_used** | `main.py` ~L2531–2551, ~L2676–2711 | `get_user_token_balance`, `get_user_status`: **tokens_used = int(gross_profit_usd × 10)** with `TOKENS_PER_USDT_GROSS = 10` (L602). |
| **Deduction log (in-memory)** | `main.py` ~L87–88, L282–296, L2963–2979 | `_deduction_logs` list; appended after each 10:15 run; exposed via `GET /admin/deduction/logs`. Not persisted to file or DB. |

### 1.2 Log keywords found in codebase

- **"token deduction"**: `main.py` (logger messages, comments), `services/daily_token_deduction.py`, `scripts/daily_token_deduction_1015utc.py`, docs.
- **"tokens_deducted"**: `services/daily_token_deduction.py` (L63, L78), `main.py` (DeductionLogEntry, logger).
- **"Bitfinex Ledgers API"** / **"Margin Funding Payment"**: `main.py` (MARGIN_FUNDING_PAYMENT_DESC, _gross_and_fees_from_ledger_entries, comments).
- **"daily_gross_profit_usd"**: `main.py` (09:40 scheduler L222–236), `models.py`, `services/daily_token_deduction.py`.
- **"choiwangai@gmail.com"**: Only in scripts (e.g. `scripts/set_choiwangai_registration.py`, `scripts/seed_gross_profit_snapshot.py`). No log line in the app is filtered by this email; logs are per `user_id`.
- **"used_tokens"**: Not a stored field. The API returns **tokens_used** (from `int(gross_profit_usd * 10)`).

---

## 2. Extracted Calculation Logic (No User-Specific Log History)

There is **no stored, chronological log history** for choiwangai@gmail.com in the codebase. Deduction logs are **in-memory only** (`_deduction_logs`), lost on restart, and not written to file or database. Below is the logic as implemented in code.

### 2.1 Gross profit (Bitfinex, 09:40 UTC)

- **Source**: Bitfinex ledgers (Margin Funding Payment) from user registration to latest.
- **Formula**: Sum of **positive** ledger amounts where description contains `"Margin Funding Payment"`.
- **Your values**: 2.181577 + 24.080038 + 36.190726 + 6.477932 + 3.271661 = **72.201934 USD** → stored as `user_profit_snapshot.gross_profit_usd`.
- **Daily delta** (for 10:15): `daily_gross_profit_usd = current_cumulative_gross - last_daily_cumulative_gross` (or full current if first run). Stored in `user_profit_snapshot.daily_gross_profit_usd`.

### 2.2 Daily token deduction (10:15 UTC)

- **Input**: `daily_gross_profit_usd` from `user_profit_snapshot` (set at 09:40).
- **Rule**: `tokens_deducted = daily_gross_profit_usd` (**1:1 USD**).
- **Update**: `tokens_remaining = max(0, tokens_remaining - tokens_deducted)`; `last_gross_usd_used = daily_gross_profit_usd`.

So: **daily_deduction (tokens) = daily_gross_profit_usd (same number in USD)**. No ×10 here.

### 2.3 used_tokens (tokens_used) in APIs

- **Endpoints**: `GET /user-token-balance/{user_id}`, `GET /user-status/{user_id}`.
- **Formula**: `tokens_used = int(gross_profit_usd * TOKENS_PER_USDT_GROSS)` with **TOKENS_PER_USDT_GROSS = 10** (`main.py` L602).
- So: **tokens_used = gross_profit_usd × 10** (integer).

Example: gross_profit_usd = 72.2 → tokens_used = 722; gross_profit_usd = 73.9 → tokens_used = 739.

---

## 3. Analysis: Why used_tokens Shows 739 Instead of 72.2

### 3.1 Unit mismatch (72.2 vs 739)

- **72.2** is **gross profit in USD** (sum of Margin Funding Payment).
- **739** is **tokens used** (same gross, converted to tokens by the rule **1 USD = 10 tokens**).
- So **72.2 USD → 722 tokens** (or 739 if the stored gross is **73.9 USD**). The code does **not** show “72.2” as “used_tokens”; it correctly shows **tokens_used = gross_profit_usd × 10**.

### 3.2 Is there a math error?

- **No.**  
  - Daily deduction: 1:1 (daily_gross_profit_usd = tokens_deducted).  
  - Display of “tokens used”: gross_profit_usd × 10.  
- So 739 is consistent with **gross_profit_usd = 73.9** in `user_profit_snapshot` (e.g. 72.2 + ~1.7 from another day or a later update).

### 3.3 Correct Margin Funding Payment data?

- Gross profit is computed from Bitfinex ledger entries with description **"Margin Funding Payment"** and positive amounts summed in `_gross_and_fees_from_ledger_entries`. So the system is designed to pull the correct field. Without a live run or saved ledger dump we cannot confirm the exact five values you listed for choiwangai in production.

### 3.4 Mismatch between Gross Profit (72.20) and used_tokens (739)?

- **Gross profit 72.20 USD** and **used_tokens 739** are **not** a bug in the formula: 739 = 73.9 × 10. So either:
  - The snapshot **gross_profit_usd** used for tokens_used is **73.9** (not 72.2), or  
  - Different endpoints/sources are used: e.g. Profit Center shows 72.20 from one source (e.g. `?source=db` or cached), while user-status/token-balance uses 73.9 from `user_profit_snapshot` (e.g. after a later 09:40 or manual update).  
- So the “mismatch” is either **unit confusion** (USD vs tokens) or **different gross values** in different code paths (72.2 vs 73.9).

---

## 4. Root Cause of 739 Used Tokens (Plain-English)

- **used_tokens** is **tokens used**, not USD. The rule is **1 USD gross profit = 10 tokens used**.
- So **72.2 USD → 722 tokens**, and **73.9 USD → 739 tokens**.
- So **739 means the backend is using a gross profit of 73.9 USD** when it computes tokens_used (from `user_profit_snapshot.gross_profit_usd`).
- There is **no multiplication bug**: the design is “gross × 10 = tokens_used”. The only way to see 739 is that the stored gross is 73.9 (or 739/10). If you expect to see **72.2** in the UI, that should be the **Gross Profit (USD)** field, not **Tokens used**. If you expect **tokens used** to equal **72** (≈ 72.2×10), then the snapshot’s `gross_profit_usd` may have been updated to 73.9 elsewhere (e.g. another 09:40 run or a different refresh).

---

## 5. Token Deduction Logs: What Exists and What Doesn’t

- **No persisted token deduction logs** for choiwangai (or any user) in the repo. No file or DB table holds a chronological history of deductions.
- **In-memory only**: The 10:15 run appends to `_deduction_logs` and logs one line per user per run via `logger.info("token_deduction user_id=... gross_profit=... tokens_deducted=... new_tokens_remaining=... ts=...")`. So you only get a history if you (1) run the backend, (2) let 10:15 (or manual trigger) run, and (3) call `GET /admin/deduction/logs` before restart; and logs are not per-email but per user_id.

So: **no token deduction logs found in the codebase** that can be “extracted” as a timestamped list for choiwangai@gmail.com.

---

## 6. Suggested Code Snippet to Add Critical Logs (Optional)

If you want to **capture** deduction logic and DB writes for future runs (e.g. for choiwangai’s user_id), you can add logs like below. This is a **snippet only**; no other code was modified.

- **Daily deduction (service)** – log inputs and result per user:

```python
# In services/daily_token_deduction.py, inside run_daily_token_deduction, in the loop over rows:
# Right after: daily_gross = float(daily_gross)
import logging
_log = logging.getLogger(__name__)
_log.info(
    "deduction_calc user_id=%s daily_gross_profit_usd=%s tokens_before=%s tokens_deducted_1to1=%s new_tokens_remaining=%s",
    user_id, daily_gross, tokens_before, daily_gross, new_tokens,
)
```

- **09:40 gross profit** – log what’s written to snapshot:

```python
# In main.py, after snap.daily_gross_profit_usd = daily and similar assignments (e.g. after db.commit() around L237):
logger.info(
    "gross_0940 user_id=%s gross_profit_usd=%s daily_gross_profit_usd=%s last_daily_cumulative_gross=%s",
    uid, result.gross_profit, daily, snap.last_daily_cumulative_gross,
)
```

- **used_tokens (API)** – log when returning token balance / user-status:

```python
# In main.py, in get_user_token_balance (and optionally in get_user_status), before return:
logger.info(
    "token_balance_api user_id=%s gross_profit_usd=%s tokens_used_gross_x10=%s tokens_remaining=%s",
    user_id, gross, tokens_used, tokens_remaining,
)
```

Then run the app, trigger 09:40 and 10:15 (or manual deduction), and call the token-balance/user-status endpoint; collect logs and filter by `user_id` for choiwangai to get a timestamped list of calculations and DB writes.

---

## 7. Summary Table

| Question | Answer |
|----------|--------|
| Where are token deduction logs? | In-memory only (`_deduction_logs`); `GET /admin/deduction/logs`; no file/DB history. |
| Full log history for choiwangai? | Not available; no persisted per-user, chronological deduction log. |
| Why 739 vs 72.2? | 72.2 is USD; 739 is tokens (gross × 10). 739 implies gross = 73.9 USD in the snapshot. |
| Math error (e.g. ×10)? | No. Design is 1 USD = 10 tokens for **tokens_used**; daily deduction is 1:1 USD. |
| Correct Margin Funding Payment? | Code sums positive “Margin Funding Payment” ledger amounts; no bug in that logic. |
| Mismatch Gross 72.20 vs used_tokens 739? | Either different sources (72.2 vs 73.9) or unit confusion (USD vs tokens). |
