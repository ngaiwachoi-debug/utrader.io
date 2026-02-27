# USDT Withdrawal Audit Log Format

Admin actions on USDT withdrawals and USDT Credit are recorded in the **admin_audit_log** table and exposed via **Admin → Audit logs**.

## Table: `admin_audit_log`

| Column   | Description                          |
|----------|--------------------------------------|
| `id`     | Unique log entry ID                  |
| `ts`     | Timestamp (UTC)                      |
| `email`  | Admin email (e.g. ngaiwanchoi@gmail.com) |
| `action` | Action identifier                    |
| `detail` | JSON string with action-specific data |

## Withdrawal-Related Actions

### `withdrawal_approve`

When admin approves a withdrawal request.

**detail** (JSON):

- `withdrawal_id`: int – request ID  
- `user_id`: int – user who requested  
- `amount`: float – approved amount (USDT Credit)

### `withdrawal_reject`

When admin rejects a withdrawal request.

**detail** (JSON):

- `withdrawal_id`: int – request ID  
- `user_id`: int – user who requested  
- `rejection_note`: string | null – optional reason shown to user  

On reject, the locked USDT Credit is returned to the user’s balance (no deduction).

### `usdt_adjust`

When admin adds or deducts USDT Credit for a user (Admin → USDT Credit → Adjust).

**detail** (JSON):

- `user_id`: int  
- `amount`: float (positive = credit, negative = debit)  
- `new_balance`: float – balance after adjustment  

## Query Examples

- All withdrawal approvals: `action = 'withdrawal_approve'`
- All withdrawal rejections: `action = 'withdrawal_reject'`
- All USDT adjustments for a user: `action = 'usdt_adjust'` and `detail` contains `"user_id": <id>`

Logs are **append-only**; no delete or update of past entries.
