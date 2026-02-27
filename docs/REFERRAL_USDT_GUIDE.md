# Referral & USDT Credit Guide

## User Guide

### Referral Program (3-Level)

- **Your referral code** is shown in **Referral & USDT** (sidebar). Share your unique link or code so others can sign up; you earn USDT Credit when they burn **purchased** tokens (not the free 150).
- **Reward rates** (per purchased token burned by a referred user):
  - **Level 1** (direct referrer): **0.0015** USDT Credit  
  - **Level 2** (referrer’s referrer): **0.0005** USDT Credit  
  - **Level 3** (level 2’s referrer): **0.0001** USDT Credit  
- **Total USDT Credit earned** is shown on the Referral & USDT page and comes only from these referral rewards.

### USDT Credit

- USDT Credit is a **bookkeeping balance** (1:1 with USDT). It is **not** an on-chain token.
- You earn it **only** via referral rewards (see above).
- **Available balance** = total USDT Credit minus any amount **locked** by pending withdrawal requests.

### Withdrawal Process (Manual Admin Approval)

1. **Set your USDT address** in **Settings → General → USDT Withdrawal Address** (TRC20 `T...` or ERC20 `0x...`). Save before requesting a withdrawal.
2. **Request a withdrawal** from **Referral & USDT**: enter amount (minimum 1 USDT Credit, configurable by admin) and submit. The request is created with status **Pending**.
3. **Locked amount**: The requested amount is **reserved** (locked) until the request is approved or rejected. You cannot submit another pending request until the current one is resolved.
4. **Admin action**:
   - **Approved**: Your USDT Credit balance is reduced by the amount; you see status **Approved**. Admin processes the payout off-platform (no automatic hot wallet send).
   - **Rejected**: The locked amount is returned to your balance; you see status **Rejected** and optionally an admin note.
5. **Withdrawal history** (Referral & USDT) shows all requests with Date, Amount, Address, Status (Pending/Approved/Rejected), and Note (for rejections).

---

## Admin Guide

### Referrals

- **Admin → Referrals**: Table of users with referral code, referrer, downline count, and total referral earnings (USDT Credit from L1/L2/L3).
- **View tree**: Use “View tree” to see a user’s L1/L2/L3 uplines and downline count. No recursion; max 3 levels.

### USDT Credit

- **Admin → USDT Credit**: Table of all users’ USDT Credit balance, **locked (pending)** amount, total earned, and total withdrawn. **Adjust** (add/deduct) is audit-logged.

### Withdrawals (Manual Approval Only)

- **Admin → Withdrawals** (or **USDT Withdrawals**): List all withdrawal requests. Filter by status (Pending / Approved / Rejected) and optionally by user.
- **Pending** rows are highlighted. For each pending request:
  - **Approve**: Confirms the request; deducts the amount from the user’s USDT Credit and marks it approved. You process the actual USDT payout off-platform.
  - **Reject**: Optional “Reason for rejection” (visible to the user); unlocks the amount back to the user’s balance and marks the request rejected.
- Admin **cannot edit** the requested amount; only approve or reject as submitted.
- Minimum withdrawal (e.g. 1 USDT Credit) is configurable in **Admin Settings**.

### Audit

- All admin actions (approve/reject withdrawal, USDT adjust) are written to the audit log (email, timestamp, action, detail).
