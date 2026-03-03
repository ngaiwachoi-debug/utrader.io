import { defineConfig, devices } from "@playwright/test"

/**
 * E2E config for dashboard bot start/stop UI.
 * Run with: npx playwright test
 * Start app first: npm run dev (or set webServer to start it).
 * For full bot flow tests, log in as a user (e.g. id 2) and run once with --headed,
 * then save storage: npx playwright test --project=chromium --headed
 * (or use storageState in the test for pre-saved auth).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  /* Start dev server when not already running (optional). */
  webServer: process.env.CI
    ? { command: "npm run dev", url: "http://localhost:3000", reuseExistingServer: false, timeout: 120000 }
    : undefined,
})
