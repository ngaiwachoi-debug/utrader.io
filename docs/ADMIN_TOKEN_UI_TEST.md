# Admin Token Add/Deduct – UI test

## Quick check (backend only)

From project root:

```bash
python tests/test_admin_token_add_deduct.py
```

Expected: `admin add/deduct tokens: OK` and `All tests passed.`

## Manual UI test

1. **Start backend** (from project root):
   ```bash
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

2. **Start frontend** (from `frontend/`):
   ```bash
   npm run dev
   ```

3. **Log in as admin**  
   Open the app (e.g. http://localhost:3000), sign in with the account that has `ADMIN_EMAIL` in `.env`.

4. **Open admin**  
   Go to `/admin` (or `/en/admin`), then click a user to open their detail page (e.g. `/admin/users/2`).

5. **Add tokens**
   - In "Token balance", enter a number in **Amount to add** (e.g. `10`).
   - Click **Add tokens**.
   - You should see: green message like `Added 10 tokens. New balance: …`, and "Remaining" / "Total added" updated.
   - Backend log should show: `admin_token_add process_start`, `before_amend`, `db_amended`.

6. **Deduct tokens**
   - Enter a number in **Amount to deduct** (e.g. `5`).
   - Click **Deduct tokens**.
   - You should see: green message like `Deducted 5 tokens. New balance: …`, and "Remaining" updated.
   - Backend log should show: `admin_token_deduct process_start`, `before_amend`, `db_amended`.

7. **Errors**
   - Leave amount empty: **Add tokens** / **Deduct tokens** stay disabled.
   - Enter 0 or negative: buttons stay disabled.
   - If you see a red message (e.g. "Error 403"), check backend logs and admin email in `.env`.

## Backend logs (what admin sees)

- **Add:** `admin_token_add process_start` → `before_amend` (balance before) → `db_amended` (balance after).
- **Deduct:** `admin_token_deduct process_start` → `before_amend` → `db_amended`.
- On validation failure: `admin_token_add validation_failed` or `user_not_found`.
