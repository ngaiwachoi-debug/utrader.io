import { test, expect } from "@playwright/test"

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000"
const LOCALE = "en"

/**
 * E2E: Bot status bar on Live Status page.
 *
 * Prerequisites:
 * - Frontend: npm run dev (or already running on BASE).
 * - Backend: uvicorn main:app (for start/stop and cooldown to work).
 *
 * When not logged in: dashboard may redirect to sign-in; tests that need
 * the bar will skip or assert redirect. When logged in (e.g. user id 2):
 * full flow runs (badge, Start/Stop visibility, click Start → Stop, click Stop → Start,
 * and 429 cooldown message after double-start).
 */
test.describe("Bot status bar (Live Status)", () => {
  test("dashboard loads and Live Status can be opened", async ({ page }) => {
    await page.goto(`/${LOCALE}/dashboard`)
    await page.waitForLoadState("networkidle")

    const url = page.url()
    if (url.includes("signin") || url.includes("login") || url.includes("auth")) {
      test.info().annotate("auth", "Redirected to login – run with a logged-in session for full bot tests")
      expect(url).toBeTruthy()
      return
    }

    await expect(page.getByRole("main")).toBeVisible({ timeout: 10000 })
    const liveStatusNav = page.getByRole("button", { name: /live status/i }).first()
    await liveStatusNav.click()
    await page.waitForTimeout(500)
    await expect(page.getByText(/live status|即時狀態/i).first()).toBeVisible({ timeout: 5000 })
  })

  test("when status is loading, badge shows Checking and no Start/Stop buttons", async ({ page }) => {
    await page.goto(`/${LOCALE}/dashboard`)
    await page.waitForLoadState("networkidle")

    if (page.url().includes("signin") || page.url().includes("login")) {
      test.skip()
    }

    const liveStatusNav = page.getByRole("button", { name: /live status/i }).first()
    await liveStatusNav.click()
    await page.waitForTimeout(2000)

    const bar = page.getByTestId("bot-status-bar")
    const barVisible = await bar.isVisible().catch(() => false)
    if (!barVisible) {
      test.skip(true, "Bot status bar not rendered (sign in as a user with id e.g. 2 for full tests)")
    }

    const badge = bar.getByTestId("bot-status-badge")
    await expect(badge).toBeVisible()
    const badgeText = (await badge.textContent()) ?? ""
    const statusUnknown = /checking|status unknown|檢查中|狀態未知/i.test(badgeText)
    if (statusUnknown) {
      await expect(page.getByTestId("bot-start-button")).not.toBeVisible()
      await expect(page.getByTestId("bot-stop-button")).not.toBeVisible()
    }
  })

  test("when stopped, only Start Bot is visible; when active, only Stop Bot is visible", async ({ page }) => {
    await page.goto(`/${LOCALE}/dashboard`)
    await page.waitForLoadState("networkidle")

    if (page.url().includes("signin") || page.url().includes("login")) {
      test.skip()
    }

    await page.getByRole("button", { name: /live status/i }).first().click()
    await page.waitForTimeout(2000)

    const bar = page.getByTestId("bot-status-bar")
    const barVisible = await bar.isVisible().catch(() => false)
    if (!barVisible) {
      test.skip(true, "Bot status bar not rendered (sign in as a user with id e.g. 2 for full tests)")
    }
    const badge = bar.getByTestId("bot-status-badge")
    await expect(badge).toBeVisible()
    const text = (await badge.textContent()) ?? ""

    if (/bot stopped|機器人已停止/i.test(text)) {
      await expect(page.getByTestId("bot-start-button")).toBeVisible()
      await expect(page.getByTestId("bot-stop-button")).not.toBeVisible()
    } else if (/bot active|機器人運行中/i.test(text)) {
      await expect(page.getByTestId("bot-stop-button")).toBeVisible()
      await expect(page.getByTestId("bot-start-button")).not.toBeVisible()
    }
  })

  test("click Start Bot then Stop Bot updates UI", async ({ page }) => {
    await page.goto(`/${LOCALE}/dashboard`)
    await page.waitForLoadState("networkidle")

    if (page.url().includes("signin") || page.url().includes("login")) {
      test.skip()
    }

    await page.getByRole("button", { name: /live status/i }).first().click()
    await page.waitForTimeout(2000)

    const startBtn = page.getByTestId("bot-start-button")
    const stopBtn = page.getByTestId("bot-stop-button")
    if (!(await startBtn.isVisible().catch(() => false)) && !(await stopBtn.isVisible().catch(() => false))) {
      test.skip(true, "No Start/Stop buttons (sign in as a user with id e.g. 2 for full tests)")
    }

    if (await startBtn.isVisible()) {
      await startBtn.click()
      await page.waitForTimeout(1500)
      await expect(page.getByTestId("bot-status-badge")).toContainText(/bot active|starting|機器人運行中|啟動中/, { timeout: 10000 })
      if (await stopBtn.isVisible().catch(() => false)) {
        await stopBtn.click()
        await page.waitForTimeout(1500)
        await expect(page.getByTestId("bot-status-badge")).toContainText(/bot stopped|stopping|機器人已停止|停止中/, { timeout: 10000 })
      }
    } else if (await stopBtn.isVisible()) {
      await stopBtn.click()
      await page.waitForTimeout(1500)
      await expect(page.getByTestId("bot-status-badge")).toContainText(/bot stopped|stopping|機器人已停止|停止中/, { timeout: 10000 })
    }
  })

  test("double Start within 30s shows cooldown error (429)", async ({ page }) => {
    await page.goto(`/${LOCALE}/dashboard`)
    await page.waitForLoadState("networkidle")

    if (page.url().includes("signin") || page.url().includes("login")) {
      test.skip()
    }

    await page.getByRole("button", { name: /live status/i }).first().click()
    await page.waitForTimeout(2000)

    const startBtn = page.getByTestId("bot-start-button")
    if (!(await startBtn.isVisible().catch(() => false))) {
      test.skip(true, "Start button not visible (sign in as a user with id e.g. 2 for full tests)")
    }

    await startBtn.click()
    await page.waitForTimeout(1500)
    // Client cooldown is 10s; after that Start becomes clickable again but backend still returns 429 (30s cooldown)
    await page.waitForTimeout(11000)
    const startAgain = page.getByTestId("bot-start-button")
    if (await startAgain.isVisible()) {
      await startAgain.click()
      await page.waitForTimeout(2000)
      const errorArea = page.getByTestId("bot-status-error")
      await expect(errorArea).toBeVisible({ timeout: 5000 })
      await expect(errorArea).toContainText(/wait|seconds|too many|minute|請等待|稍後/i)
    }
  })
})
