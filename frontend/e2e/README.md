# E2E tests (Playwright)

## Bot status bar (Live Status)

Tests in `bot-status-bar.spec.ts` cover:

- **Dashboard + Live Status:** Navigate to dashboard and open Live Status (passes even when not logged in).
- **Loading state:** When status is unknown, badge shows "Checking…" or "Status Unknown" and **no** Start/Stop buttons.
- **Stopped vs Active:** When stopped, only **Start Bot** is visible; when active, only **Stop Bot** is visible.
- **Click flow:** Start Bot → bar updates to Stop Bot; Stop Bot → bar updates to Start Bot.
- **Cooldown (429):** After starting, wait for client cooldown (10s), click **Start Bot** again; backend returns 429 and the error area shows "wait X seconds" (or similar).

When no user is signed in, the bot-status bar is not rendered; tests that depend on it **skip** with a message so the suite still passes.

## Prerequisites

1. **Frontend** running, e.g. `npm run dev` (default `http://localhost:3000`).
2. **Backend** running (for start/stop and 429 cooldown), e.g. from repo root: `python -m uvicorn main:app --host 127.0.0.1 --port 8000`.
3. **Logged-in user** (e.g. user id 2) for full bot flow. If not logged in, bot-specific tests skip.

## Run

```bash
# Install browsers (once)
npx playwright install chromium

# Run all E2E tests
npm run test:e2e

# Run with UI
npm run test:e2e:ui

# Custom base URL
PLAYWRIGHT_BASE_URL=http://localhost:3001 npm run test:e2e
```

## Auth for full flow

To run the full bot start/stop and 429 cooldown tests:

1. Start frontend and backend.
2. In a browser, go to the app and log in as the desired user (e.g. the one with id 2).
3. Run Playwright in **headed** mode so it uses the same origin; or save auth state once and reuse:
   - Log in manually, then run: `npx playwright test --project=chromium --headed`
   - Tests will use the current browser session when running headed.

If you run headless without saved auth, dashboard may redirect to sign-in and tests that need the bar will skip.
