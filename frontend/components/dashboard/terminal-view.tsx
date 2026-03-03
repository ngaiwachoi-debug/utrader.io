"use client"

import { useEffect, useState, useRef } from "react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useBotStatus } from "@/lib/bot-status-context"
import { getBackendToken } from "@/lib/auth"
import { Terminal } from "lucide-react"
import { BotStatusBar } from "@/components/dashboard/bot-status-bar"

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
  const botStartedAt = useRef<number>(0)
  const preRef = useRef<HTMLPreElement>(null)

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

  // Auto-scroll to bottom when new logs load
  useEffect(() => {
    preRef.current?.scrollTo({ top: preRef.current.scrollHeight, behavior: "smooth" })
  }, [logLines])

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

  const idleEntries = summary?.idle_per_currency_usd
    ? Object.entries(summary.idle_per_currency_usd).filter(([, v]) => v > 0)
    : []

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6">
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

      {/* Recent activity (log lines) — fills remaining space, max viewport height, scrolls to bottom on new logs */}
      <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-border bg-card font-mono text-sm max-h-[calc(100vh-14rem)] min-h-[240px]">
        <div className="flex shrink-0 items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Recent activity (cached, refresh every {pollIntervalMs >= 60000 ? `${pollIntervalMs / 60000}m` : `${pollIntervalMs / 1000}s`})</span>
        </div>
        <pre
          ref={preRef}
          className="min-h-[120px] flex-1 overflow-auto p-4 text-muted-foreground whitespace-pre-wrap"
        >
          {terminalContent}
        </pre>
      </div>
    </div>
  )
}
