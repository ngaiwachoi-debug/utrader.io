"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useBotStatus } from "@/lib/bot-status-context"
import { getBackendToken } from "@/lib/auth"
import { Terminal, ChevronDown, ChevronRight, Copy, ArrowDown } from "lucide-react"
import { BotStatusBar } from "@/components/dashboard/bot-status-bar"

const SCROLL_THRESHOLD_PX = 50

type TerminalSummary = {
  strategy?: string
  regime?: string
  v_sigma?: number
  lag_minutes_composite?: number
  idle_per_currency_usd?: Record<string, number>
  offers_this_cycle?: { count: number; total_usd: number }
  apr_ladder_min?: number
  apr_ladder_max?: number
  next_rebalance_sec?: number
  last_insight?: string
  status?: string
} | null

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

/** Tier-based terminal poll intervals (ms): Trial/Free 4h, Pro 5m, AI Ultra 30m, Whales 10m. */
const TERMINAL_POLL_BY_TIER_MS: Record<string, number> = {
  trial: 14400000,   // 4h
  free: 14400000,     // 4h
  pro: 300000,       // 5m
  ai_ultra: 1800000, // 30m
  whales: 600000,    // 10m
}
const FIRST_5_MIN_POLL_MS = 10_000
const FIRST_5_MIN_MS = 5 * 60 * 1000

/**
 * Terminal tab: shows trading box terminal output for the signed-in user.
 * Poll interval: 10s for first 5 min after Start (or tab open), then tier-based (Trial 4h, Pro 5m, AI Ultra 30m, Whales 10m).
 */
export function TerminalView() {
  const t = useT()
  const userId = useCurrentUserId()
  const botCtx = useBotStatus()
  const [logLines, setLogLines] = useState<string[]>([])
  const [summary, setSummary] = useState<TerminalSummary>(null)
  const [planTier, setPlanTier] = useState<string>("trial")
  const [pollIntervalMs, setPollIntervalMs] = useState(FIRST_5_MIN_POLL_MS)
  const [checksOpen, setChecksOpen] = useState(false)
  const [showScrollToBottom, setShowScrollToBottom] = useState(false)
  const [copyFeedback, setCopyFeedback] = useState(false)
  const botStartedAt = useRef<number>(0)
  const logContainerRef = useRef<HTMLPreElement | null>(null)
  const userHasScrolledUp = useRef(false)

  // Fetch user-status for plan_tier when tab mounts
  useEffect(() => {
    if (userId == null) return
    const token = getBackendToken()
    token.then((tkn) => {
      const headers: HeadersInit = tkn ? { Authorization: `Bearer ${tkn}` } : {}
      return fetch(`${API_BASE}/user-status/${userId}`, { credentials: "include", headers })
    }).then((res) => (res.ok ? res.json() : { plan_tier: "trial" }))
      .then((data) => {
        const raw = (data.plan_tier ?? "trial").toString().trim().toLowerCase()
        const tier = raw === "ai ultra" ? "ai_ultra" : raw.replace(/\s+/g, "_")
        setPlanTier(tier)
      })
      .catch(() => setPlanTier("trial"))
  }, [userId])

  // When we first see bot starting/running, record time; use 10s poll for first 5 min from then, then tier-based
  useEffect(() => {
    if (userId == null) return
    const startingOrRunning = botCtx?.isStarting === true || botCtx?.botActive === true
    if (startingOrRunning && botStartedAt.current === 0) botStartedAt.current = Date.now()
    const tierMs = TERMINAL_POLL_BY_TIER_MS[planTier] ?? TERMINAL_POLL_BY_TIER_MS.trial
    const inFirst5Min = botStartedAt.current > 0 && Date.now() - botStartedAt.current < FIRST_5_MIN_MS
    setPollIntervalMs(inFirst5Min ? FIRST_5_MIN_POLL_MS : tierMs)
  }, [userId, planTier, botCtx?.isStarting, botCtx?.botActive])

  useEffect(() => {
    if (userId == null) {
      setLogLines([])
      setSummary(null)
      return
    }
    const fetchLogs = async () => {
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      fetch(`${API_BASE}/terminal-logs/${userId}`, { credentials: "include", headers })
        .then((res) => (res.ok ? res.json() : { lines: [], summary: null }))
        .then((data) => {
          setLogLines(Array.isArray(data.lines) ? data.lines : [])
          setSummary(data.summary ?? null)
        })
        .catch(() => {
          setLogLines([])
          setSummary(null)
        })
    }
    fetchLogs()
    const interval = setInterval(fetchLogs, pollIntervalMs)
    return () => clearInterval(interval)
  }, [userId, pollIntervalMs])

  const handleLogScroll = useCallback(() => {
    const el = logContainerRef.current
    if (!el) return
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - SCROLL_THRESHOLD_PX
    if (atBottom) {
      userHasScrolledUp.current = false
      setShowScrollToBottom(false)
    } else {
      userHasScrolledUp.current = true
      setShowScrollToBottom(true)
    }
  }, [])

  useEffect(() => {
    if (!userHasScrolledUp.current && logContainerRef.current) {
      const el = logContainerRef.current
      const run = () => {
        el.scrollTop = el.scrollHeight
      }
      requestAnimationFrame(run)
    }
  }, [logLines])

  const scrollToBottom = useCallback(() => {
    const el = logContainerRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
      userHasScrolledUp.current = false
      setShowScrollToBottom(false)
    }
  }, [])

  const handleCopyLog = useCallback(async () => {
    const text = logLines.length > 0 ? logLines.join("\n") : t("dashboard.terminalPlaceholder")
    try {
      await navigator.clipboard.writeText(text)
      setCopyFeedback(true)
      setTimeout(() => setCopyFeedback(false), 2000)
    } catch {
      setCopyFeedback(false)
    }
  }, [logLines, t])

  if (userId == null) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold text-foreground">{t("sidebar.terminal")}</h1>
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted-foreground">Sign in to see the trading terminal.</p>
        </div>
      </div>
    )
  }

  const terminalContent = logLines.length > 0 ? logLines.join("\n") : t("dashboard.terminalPlaceholder")

  const checksTable: { step: number; check: string; success: string; failure: string; stateOnFailure: string }[] = [
    { step: 1, check: "API Request Authentication", success: "User is logged in (valid JWT/session; current_user exists)", failure: "Return 401 UNAUTHORIZED (Not authenticated)", stateOnFailure: "No state changes" },
    { step: 2, check: "Set Desired State", success: "bot_desired_state updated to running in DB + commit succeeds", failure: "Return 500 INTERNAL_SERVER_ERROR (Failed to update intent)", stateOnFailure: "bot_desired_state remains stopped" },
    { step: 3, check: "Token Threshold Check (Q6)", success: "Calculated token balance (total_added - total_deducted) > 0", failure: "Return 400 INSUFFICIENT_TOKENS (Tokens must be greater than 0)", stateOnFailure: "bot_desired_state stays running (intent), bot_status remains stopped" },
    { step: 4, check: "Idempotency Check (Q7)", success: "NOT (bot_status in [running, starting] AND bot_desired_state = running)", failure: "Return 200 OK (Bot already running or queued)", stateOnFailure: "No state changes (no enqueue, no bot_status update)" },
    { step: 5, check: "Vault/API Key Check", success: "User has valid API keys stored in vault", failure: "Return 400 BAD_REQUEST (Missing/invalid API keys)", stateOnFailure: "bot_desired_state = running, bot_status = stopped" },
    { step: 6, check: "Enqueue Bot Task", success: "_enqueue_bot_task succeeds (job added to ARQ queue)", failure: "Return 500 INTERNAL_SERVER_ERROR (Failed to queue bot job)", stateOnFailure: "bot_desired_state = running, bot_status = stopped" },
    { step: 7, check: "Update Bot Status", success: "bot_status updated to starting in DB + commit succeeds", failure: "Return 500 INTERNAL_SERVER_ERROR (Failed to update bot status)", stateOnFailure: "bot_desired_state = running, bot_status remains stopped" },
    { step: 8, check: "Worker Startup Reconcile", success: "Worker loads user, bot_desired_state = running (matches intent)", failure: "Worker sets bot_desired_state = stopped + bot_status = stopped (commit)", stateOnFailure: "Both states reset to stopped; worker exits" },
    { step: 9, check: "Worker Vault/Config Check", success: "Worker validates API keys/plan config (same as Step 5)", failure: "Worker sets both states to stopped (commit) + logs error", stateOnFailure: "Both states = stopped; worker exits" },
    { step: 10, check: "Worker Token Check", success: "Worker rechecks token balance > 0 (prevents race conditions)", failure: "Worker sets both states to stopped (commit) + logs Token exhaustion", stateOnFailure: "Both states = stopped; worker exits" },
    { step: 11, check: "Worker Set Running State", success: "Worker updates bot_status to running (commit)", failure: "Worker sets both states to stopped (commit) + logs Failed to start bot", stateOnFailure: "Both states = stopped; worker exits" },
    { step: 12, check: "Worker Kill-Switch Loop (Q4)", success: "bot_desired_state remains running (no stop signal) during loop iterations", failure: "Worker sets both states to stopped (commit) + cancels engine", stateOnFailure: "Both states = stopped; bot stops" },
  ]

  const idleEntries = summary?.idle_per_currency_usd
    ? Object.entries(summary.idle_per_currency_usd).filter(([, v]) => v > 0)
    : []

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-6 min-h-[calc(100vh-12rem)]">
      <BotStatusBar title={t("sidebar.terminal")} />
      <p className="text-sm text-muted-foreground -mt-2">{t("dashboard.terminalDesc")}</p>

      {/* Live strategy & status card */}
      {summary != null && (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h2 className="text-sm font-semibold text-foreground">Live strategy &amp; status</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Current IQM regime, idle funds, and last cycle.</p>
          </div>
          <div className="p-4 grid gap-3 text-sm">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="font-medium text-foreground">{summary.strategy ?? "—"}</span>
              <span className="text-muted-foreground">Regime: {summary.regime ?? "—"} (v_σ = {summary.v_sigma ?? "—"})</span>
              <span className="text-muted-foreground">Front-run: {summary.lag_minutes_composite ?? "—"} min</span>
              <span className="text-muted-foreground">Status: {summary.status ?? "—"}</span>
            </div>
            {idleEntries.length > 0 && (
              <div>
                <span className="text-muted-foreground">Idle by currency: </span>
                <span className="text-foreground">
                  {idleEntries.map(([c, v]) => `${c} ${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`).join(" · ")}
                </span>
              </div>
            )}
            {summary.offers_this_cycle != null && (
              <div>
                <span className="text-muted-foreground">Offers this cycle: </span>
                <span className="text-foreground">
                  {summary.offers_this_cycle.count} offers · ~{summary.offers_this_cycle.total_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })} USD
                </span>
              </div>
            )}
            {(summary.apr_ladder_min != null || summary.apr_ladder_max != null) && (
              <div>
                <span className="text-muted-foreground">APR ladder: </span>
                <span className="text-foreground">
                  {summary.apr_ladder_min ?? "—"}% – {summary.apr_ladder_max ?? "—"}%
                </span>
              </div>
            )}
            {summary.next_rebalance_sec != null && (
              <div>
                <span className="text-muted-foreground">Next rebalance in: </span>
                <span className="text-foreground">{Math.round(summary.next_rebalance_sec / 60)} min</span>
              </div>
            )}
            {summary.last_insight && (
              <div className="pt-1 border-t border-border/50">
                <span className="text-muted-foreground block mb-1">Last insight</span>
                <p className="text-foreground">{summary.last_insight}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Recent activity (log lines) – fills remaining space */}
      <div className="rounded-xl border border-border bg-card font-mono text-sm flex flex-col flex-1 min-h-0">
        <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/50 px-4 py-2 flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Terminal className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="text-muted-foreground text-xs truncate">
              Recent activity (cached, refresh every {pollIntervalMs >= 60000 ? `${pollIntervalMs / 60000}m` : `${pollIntervalMs / 1000}s`})
            </span>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={handleCopyLog}
              className="rounded-md border border-border bg-background px-2 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors inline-flex items-center gap-1.5"
            >
              <Copy className="h-3.5 w-3.5" />
              {copyFeedback ? t("dashboard.terminalCopied") : t("dashboard.terminalCopy")}
            </button>
            {showScrollToBottom && (
              <button
                type="button"
                onClick={scrollToBottom}
                className="rounded-md border border-border bg-background px-2 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors inline-flex items-center gap-1.5"
              >
                <ArrowDown className="h-3.5 w-3.5" />
                {t("dashboard.terminalScrollToBottom")}
              </button>
            )}
          </div>
        </div>
        <pre
          ref={logContainerRef}
          onScroll={handleLogScroll}
          role="log"
          aria-label="Trading terminal output"
          className="flex-1 min-h-[200px] overflow-auto p-4 text-muted-foreground whitespace-pre-wrap leading-relaxed"
        >
          {terminalContent}
        </pre>
      </div>

      {/* Collapsible: Developer – Start bot checks */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <button
          type="button"
          onClick={() => setChecksOpen((o) => !o)}
          className="w-full flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2 text-left hover:bg-muted/70 transition-colors"
        >
          {checksOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
          <h2 className="text-sm font-semibold text-foreground">Developer: Start bot checks &amp; outcomes</h2>
        </button>
        {checksOpen && (
          <>
            <p className="text-xs text-muted-foreground px-4 pt-2">Success condition, failure outcome, and state changes on failure per step.</p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="p-2 font-medium text-foreground">#</th>
                    <th className="p-2 font-medium text-foreground">Check</th>
                    <th className="p-2 font-medium text-foreground">Success condition</th>
                    <th className="p-2 font-medium text-foreground">Failure outcome</th>
                    <th className="p-2 font-medium text-foreground">State changes on failure</th>
                  </tr>
                </thead>
                <tbody>
                  {checksTable.map((row) => (
                    <tr key={row.step} className="border-b border-border/50 hover:bg-muted/20">
                      <td className="p-2 text-muted-foreground font-mono">{row.step}</td>
                      <td className="p-2 font-medium text-foreground">{row.check}</td>
                      <td className="p-2 text-muted-foreground max-w-[200px]">{row.success}</td>
                      <td className="p-2 text-destructive/90 max-w-[200px]">{row.failure}</td>
                      <td className="p-2 text-muted-foreground max-w-[220px]">{row.stateOnFailure}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
