# When tokens are added (reasons)

Token balance can **increase** only when one of the following runs. **Auto-deduction (10:30 UTC and manual-trigger backfill) only deducts**; it never adds tokens.

## All reasons tokens are added

| Reason | Where | When |
|--------|--------|------|
| **registration** | `main.py` (signup) | New user registers; one-time award (e.g. 150 tokens). |
| **admin_add** | `main.py` ? `POST /admin/users/{id}/tokens/add` | Admin adds tokens for one user. |
| **admin_bulk_add** | `main.py` ? `POST /admin/tokens/bulk-add` | Admin bulk add; also applies referral rewards. |
| **deposit_usd** | `main.py` ? token deposit (Stripe or dev bypass) | User pays USD ? tokens (1 USD = 100 tokens). |
| **subscription_monthly** | `main.py` ? Stripe webhook or `POST /api/v1/subscription/bypass` | Subscription payment (e.g. Whales monthly = 40k tokens). |
| **subscription_yearly** | Same | Subscription yearly payment. |
| **deduction_rollback** | Several places | **Refund** of previously deducted tokens. |

## When `deduction_rollback` is used (balance goes up after a deduction)

1. **Admin rollback**  
   `POST /admin/deduction/rollback/{user_id}/{date}` ? admin undoes deduction for that user/date; tokens are added back.

2. **Scripts**  
   - `scripts/rollback_uid2_two_days.py` ? rolls back user 2 for today and yesterday.  
   - `scripts/run_manual_trigger_test_uid2.py` ? at the end it rolls back the two days it tested.  
   - `scripts/reverse_deductions_*.py`, `scripts/reverse_today_set_yesterday_deducted.py`, etc.

3. **Reconciliation (overcharge)**  
   Reconciliation no longer auto-adds tokens. If we overcharged (stored snapshot higher than reconciled value), we only clear the cache and log a warning; refunds are done only via admin rollback or scripts.

## Your data (user 3 and 32)

- Rows in **deduction_log** are **deductions only** (each row = one deduction; `tokens_remaining_after` goes down or stays 0).  
- If you see **balance go up** later (e.g. in `user_token_balance` or in a later deduction row's "before" balance), it is from one of the add reasons above (e.g. **deduction_rollback** from rollback script, admin rollback, or reconciliation; or **subscription** / **admin_add** / **deposit_usd**).  
- **Auto-deduction and manual-trigger backfill never add tokens**; they only call `deduct_tokens`. The only "add" tied to deductions is an explicit **rollback** (admin or script); reconciliation does not auto-refund.

## Summary

- **Auto-deduction**: only subtracts; never adds.  
- **Manual trigger (backfill)**: only subtracts; never adds.  
- **Balance increases** always come from: registration, admin add, deposit_usd, subscription, or **deduction_rollback** (admin rollback or test/rollback scripts only; reconciliation does not auto-refund).
