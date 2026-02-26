# API Keys & Secrets – GitHub Exposure Check

## Summary

A scan found **hardcoded secrets in files that are tracked by git** (and thus may be on GitHub). Those have been removed from the codebase. You must **rotate any credentials that were ever committed**.

---

## What was exposed (and fixed)

| File | What was exposed | Fix applied |
|------|------------------|-------------|
| **database.py** | `DATABASE_URL` with Neon DB password (`npg_pyaiQAxCnP84`) and host | Removed fallback; app now requires `DATABASE_URL` in `.env` and raises if missing. |
| **debug_bitfinex_connection.py** | Bitfinex `API_KEY` and `API_SECRET` | Now reads `BFX_KEY` and `BFX_SECRET` from env; exits with a message if unset. |
| **scripts/save_api_keys_for_user.py** | Default `BFX_KEY`, `BFX_SECRET`, and `GEMINI_KEY` (real-looking values) | No default secrets; requires `BFX_KEY` and `BFX_SECRET` in env and exits if missing. |

---

## What is not tracked (OK if kept local only)

- **frontend/.env.local** – Ignored by `frontend/.gitignore` (`.env*.local`). **Do not commit.** It contained (or may contain) `GOOGLE_CLIENT_SECRET`, `NEXTAUTH_SECRET`, and `DATABASE_URL`; keep it only on your machine and in env-based config.
- **scripts/test_daily_scheduler_and_failures.py** – Contains test Bitfinex keys but was **not** in `git ls-files` (either untracked or ignored). Do not add real keys to this file; use env vars if you commit it.

---

## What you must do now

1. **Rotate every credential that ever appeared in the repo (or in history):**
   - **Neon (Postgres):** New password in Neon dashboard; update `DATABASE_URL` in `.env` (and anywhere else you use it).
   - **Bitfinex:** Revoke/regenerate the API keys that were in `debug_bitfinex_connection.py` and `save_api_keys_for_user.py`; create new keys and put them only in `.env` / env.
   - **Google OAuth:** If `GOOGLE_CLIENT_SECRET` was ever committed (e.g. in `frontend/.env.local` and that file was ever pushed), regenerate the client secret in Google Cloud Console and update your env.
   - **NextAuth:** If `NEXTAUTH_SECRET` was ever committed, generate a new secret and update `.env` / env.
   - **Gemini:** If the key in `save_api_keys_for_user.py` was real, revoke/regenerate it in Google AI Studio and use the new key only via env.

2. **Ensure secrets never get committed again:**
   - Use only environment variables or `.env` (and keep `.env` in `.gitignore`).
   - Do not add fallback/default values for real API keys or passwords in code.
   - Run `git status` and `git diff` before pushing to ensure no `.env` or `*.env.local` files are staged.

3. **If the repo was already pushed to GitHub:**
   - Rotate all credentials listed above immediately.
   - Consider using [GitHub’s secret scanning](https://docs.github.com/en/code-security/secret-scanning) and [git history cleanup](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) if secrets were pushed in the past.

---

## Safe pattern from now on

- **Backend:** Put `DATABASE_URL`, `STRIPE_*`, `BFX_KEY`, `BFX_SECRET`, `GEMINI_KEY`, `NEXTAUTH_SECRET`, etc. in a `.env` file at project root (or in your deployment env). Ensure `.env*` is in `.gitignore`.
- **Frontend:** Use `NEXT_PUBLIC_*` only for non-secret config. Keep `GOOGLE_CLIENT_SECRET`, `NEXTAUTH_SECRET`, and any API keys in `.env.local` and do not commit that file.
- **Scripts:** Require env vars (e.g. `BFX_KEY`, `BFX_SECRET`) and exit with a clear message if they are missing; do not embed real keys as defaults.
