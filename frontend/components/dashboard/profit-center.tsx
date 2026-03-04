"use client"

import { useEffect, useMemo, useState } from "react"
import {
  DollarSign,
  Clock,
  RefreshCw,
  Wallet,
} from "lucide-react"
import { Spinner } from "@/components/ui/spinner"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { getBackendToken } from "@/lib/auth"
import { useLendingStats, useUserStatus, useDeductionMultiplier, type LendingStatsTrade } from "@/lib/dashboard-data-context"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts"

const API_BACKEND = "/api-backend"
const REFRESH_COOLDOWN_SEC = 15

type TradeForChart = { mts_create: number; amount: number; interest_usd: number }
const tradeToChart = (t: LendingStatsTrade): TradeForChart => ({
  mts_create: t.mts_create,
  amount: t.amount,
  interest_usd: t.interest_usd,
})

/** Chart range from 7d/30d/90d relative to today (so trades are not filtered out by wrong year). */
function chartRangeFromTimeRange(timeRange: string): { start: Date; end: Date } {
  const end = new Date()
  end.setHours(23, 59, 59, 999)
  const start = new Date(end)
  const days = timeRange === "90d" ? 90 : timeRange === "7d" ? 7 : 30
  start.setDate(start.getDate() - days)
  start.setHours(0, 0, 0, 0)
  return { start, end }
}

/** Derive chart time series from funding trades (no extra API). Updates when gross profit / lending data updates. */
function deriveChartHistoryFromTrades(
  trades: TradeForChart[],
  rangeStart: Date,
  rangeEnd: Date
): { date: string; volume: number; interest: number }[] {
  const start = rangeStart.getTime()
  const end = rangeEnd.getTime()
  const byDay = new Map<string, { volume: number; interest: number }>()
  for (const t of trades) {
    const ms = typeof t.mts_create === "number" ? t.mts_create : 0
    if (ms < start || ms > end) continue
    const d = new Date(ms)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    const prev = byDay.get(key) ?? { volume: 0, interest: 0 }
    byDay.set(key, {
      volume: prev.volume + Math.abs(typeof t.amount === "number" ? t.amount : 0),
      interest: prev.interest + (typeof t.interest_usd === "number" ? t.interest_usd : 0),
    })
  }
  return Array.from(byDay.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([dateKey, { volume, interest }]) => {
      const [y, m, d] = dateKey.split("-")
      return { date: `${m}-${d}`, volume: Math.round(volume * 100) / 100, interest: Math.round(interest * 100) / 100 }
    })
}

const chartData = [
  { date: "02-19", volume: 12400, interest: 32 },
  { date: "02-20", volume: 18200, interest: 48 },
  { date: "02-21", volume: 22100, interest: 61 },
  { date: "02-22", volume: 15800, interest: 42 },
  { date: "02-23", volume: 24500, interest: 68 },
  { date: "02-24", volume: 19300, interest: 52 },
  { date: "02-25", volume: 21000, interest: 58 },
]

type ProfitCenterProps = { onUpgradeClick?: () => void }

export function ProfitCenter({ onUpgradeClick }: ProfitCenterProps) {
  const t = useT()
  const userId = useCurrentUserId()
  const id = userId ?? 0
  const lendingStats = useLendingStats(id)
  const userStatus = useUserStatus(id)
  const deductionMultiplier = useDeductionMultiplier()
  const [timeRange, setTimeRange] = useState("30d")
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [refreshCooldownUntil, setRefreshCooldownUntil] = useState(0)
  const [refreshCooldownSec, setRefreshCooldownSec] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [tokenBalance, setTokenBalance] = useState<{
    tokens_remaining: number
    total_tokens_added: number
    total_tokens_deducted: number
  } | null>(null)
  const [tokenBalanceLoading, setTokenBalanceLoading] = useState(true)

  const data = lendingStats.data
  const loading = lendingStats.loading && !data
  const error = lendingStats.error
  const grossProfit = data?.gross_profit ?? null
  const netProfit = data?.net_profit ?? null
  const tokensRemaining = tokenBalance?.tokens_remaining ?? userStatus.data?.tokens_remaining ?? null
  const planTierRaw = userStatus.data?.plan_tier ?? "trial"
  const planTier = (typeof planTierRaw === "string" ? planTierRaw : "trial").trim().toLowerCase().replace(/\s+/g, "_")
  const tier = planTier === "ai ultra" ? "ai_ultra" : planTier
  const isWhales = tier === "whales" || tier === "whales_ai"
  const upgradeLabelKey =
    isWhales ? null
    : tier === "ai_ultra" ? "dashboard.upgradeToWhalesAi"
    : tier === "pro" ? "dashboard.upgradeToAiUltra"
    : "dashboard.upgradeToPro"
  const lendingDataSource = lendingStats.source
  const lendingRateLimited = lendingStats.rateLimited
  const tradesCount = data?.total_trades_count ?? null
  const fundingTrades = useMemo(() => data?.trades ?? [], [data?.trades])
  const calculationBreakdown = data?.calculation_breakdown ?? null

  useEffect(() => {
    const interval = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((refreshCooldownUntil - Date.now()) / 1000))
      setRefreshCooldownSec(remaining)
    }, 1000)
    return () => clearInterval(interval)
  }, [refreshCooldownUntil])

  useEffect(() => {
    if (userId == null) {
      setTokenBalance(null)
      setTokenBalanceLoading(false)
      return
    }
    let cancelled = false
    const run = async () => {
      setTokenBalanceLoading(true)
      try {
        const token = await getBackendToken()
        if (!token || cancelled) return
        const res = await fetch(`${API_BACKEND}/api/v1/users/me/token-balance`, {
          credentials: "include",
          headers: { Authorization: `Bearer ${token}` },
        })
        if (cancelled) return
        if (res.ok) {
          const data = await res.json()
          if (!cancelled) {
            setTokenBalance({
              tokens_remaining: Number(data.tokens_remaining) ?? 0,
              total_tokens_added: Number(data.total_tokens_added) ?? 0,
              total_tokens_deducted: Number(data.total_tokens_deducted) ?? 0,
            })
          }
        } else {
          if (!cancelled) setTokenBalance(null)
        }
      } catch {
        if (!cancelled) setTokenBalance(null)
      } finally {
        if (!cancelled) setTokenBalanceLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [userId])

  // Derive chart from trades (useMemo avoids setState-in-useEffect loop when fundingTrades ref changes)
  const chartHistory = useMemo(() => {
    if (userId == null || fundingTrades.length === 0) return []
    const { start, end } = chartRangeFromTimeRange(timeRange)
    const tradesForChart = fundingTrades.map(tradeToChart)
    return deriveChartHistoryFromTrades(tradesForChart, start, end)
  }, [timeRange, userId, fundingTrades])

  const handleRefresh = async () => {
    if (userId == null) return
    if (Date.now() < refreshCooldownUntil) return
    setRefreshCooldownUntil(Date.now() + REFRESH_COOLDOWN_SEC * 1000)
    setRefreshing(true)
    try {
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/api/refresh-lending-stats`, { method: "POST", credentials: "include", headers })
      if (res.ok) await lendingStats.refetch()
    } finally {
      setRefreshing(false)
    }
  }

  if (userId == null) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold text-foreground">{t("dashboard.profitCenter")}</h1>
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted-foreground">Sign in to see your profit data.</p>
        </div>
      </div>
    )
  }

  const gross = grossProfit ?? 0
  const net = netProfit ?? 0

  return (
    <div className="flex flex-col gap-6">
      {/* Page Title */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t("dashboard.profitCenter")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("dashboard.profitCenterDesc")}
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing || loading || refreshCooldownSec > 0}
          className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing…" : refreshCooldownSec > 0 ? `${t("liveStatus.refreshIn", { n: refreshCooldownSec })}` : "Refresh Gross Profit"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Token credit – allocation breakdown like LiveStatus (total added, remaining vs used) */}
      <div className="rounded-xl border border-primary/20 bg-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <Wallet className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{t("dashboard.tokenCredit")}</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{t("dashboard.tokenUsageRule", { multiplier: deductionMultiplier })}</p>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          {tokenBalanceLoading && !tokenBalance ? (
            <span className="text-xl font-bold text-primary">…</span>
          ) : (
            <span className="text-xl font-bold text-primary">
              {tokenBalance != null
                ? `${Math.round(tokenBalance.total_tokens_added).toLocaleString()} ${t("dashboard.totalTokensAdded")}`
                : "—"}
            </span>
          )}
          {onUpgradeClick && upgradeLabelKey && (
            <button
              onClick={() => onUpgradeClick()}
              className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              {t(upgradeLabelKey)}
            </button>
          )}
        </div>
        <div className="mb-4">
          <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
            <span>{t("dashboard.tokenBreakdown")}</span>
          </div>
          <div className="h-3 w-full rounded-full bg-secondary overflow-hidden flex">
            <div
              className="h-full bg-primary transition-all"
              style={{
                width: `${(() => {
                  const total = tokenBalance?.total_tokens_added ?? 0
                  const rem = tokenBalance?.tokens_remaining ?? tokensRemaining ?? 0
                  return total > 0 ? Math.min(100, (100 * rem) / total) : 0
                })()}%`,
              }}
            />
            <div
              className="h-full bg-amber-500/80 transition-all"
              style={{
                width: `${(() => {
                  const total = tokenBalance?.total_tokens_added ?? 0
                  const used = tokenBalance?.total_tokens_deducted ?? 0
                  return total > 0 ? Math.min(100, (100 * used) / total) : 0
                })()}%`,
              }}
            />
          </div>
          <div className="flex gap-4 mt-1.5 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-primary" />
              {t("dashboard.tokensRemaining")}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-amber-500/80" />
              {t("dashboard.tokensUsed")}
            </span>
          </div>
        </div>
      </div>

      {/* Profit Stats Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {/* Gross Profit */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Gross Profit
            </span>
            <DollarSign className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            {loading && grossProfit === null ? (
              <span className="flex items-center gap-2 text-2xl font-bold text-foreground">
                <Spinner className="h-6 w-6" />
                <span className="text-muted-foreground">Loading…</span>
              </span>
            ) : (
              <span className="text-2xl font-bold text-foreground">${gross.toFixed(2)}</span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {!loading && !error && gross === 0
              ? t("dashboard.noDataYet") + " Gross comes from Bitfinex Margin Funding ledger (sum of EARNED). Use Refresh, or ensure the daily 9:40/10:00 UTC job has run and API keys are connected."
              : t("dashboard.grossProfitSinceRegistration")}
            {tradesCount != null && tradesCount > 0 && (
              <span className="ml-1"> · {tradesCount} repaid lending trade{tradesCount !== 1 ? "s" : ""} extracted</span>
            )}
            {lendingDataSource === "cache" && (
              <span className="ml-1 text-muted-foreground"> · {t("dashboard.dataCached")}</span>
            )}
            {lendingRateLimited && (
              <span className="ml-1 text-amber-600 dark:text-amber-400" title={t("dashboard.rateLimited")}> · ⚠</span>
            )}
          </p>
          {calculationBreakdown && calculationBreakdown.per_currency.length > 0 && (
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setShowBreakdown(!showBreakdown)}
                className="text-xs font-medium text-primary hover:underline"
              >
                {showBreakdown ? "Hide" : "Show"} calculation breakdown
              </button>
              {showBreakdown && (
                <div className="mt-2 rounded border border-border bg-muted/30 p-3 text-xs">
                  <p className="text-muted-foreground mb-2">{calculationBreakdown.formula_note}</p>
                  <table className="w-full table-fixed">
                    <thead>
                      <tr className="text-muted-foreground">
                        <th className="text-left font-medium">Currency</th>
                        <th className="text-right font-medium">Interest (ccy)</th>
                        <th className="text-right font-medium">Price (USD)</th>
                        <th className="text-right font-medium">Interest (USD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {calculationBreakdown.per_currency.map((row) => (
                        <tr key={row.currency} className="border-t border-border/50">
                          <td className="py-1 font-medium">{row.currency}</td>
                          <td className="py-1 text-right font-mono">{row.interest_ccy.toFixed(6)}</td>
                          <td className="py-1 text-right font-mono">{row.ticker_price_usd.toFixed(4)}</td>
                          <td className="py-1 text-right font-mono text-primary">${row.interest_usd.toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-2 border-t border-border pt-2 font-medium text-foreground">
                    Total gross USD: ${calculationBreakdown.total_gross_usd.toFixed(4)} ({calculationBreakdown.trades_count} trades)
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {(lendingDataSource === "cache" || lendingRateLimited) && (
        <p className="text-xs text-muted-foreground">
          {lendingRateLimited ? t("dashboard.rateLimited") : t("dashboard.dataCached")}
        </p>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Lending Volume Chart */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-foreground">{t("dashboard.lendingVolume24h")}</h3>
              <p className="text-xs text-muted-foreground">{t("dashboard.lendingVolumeDesc")}</p>
            </div>
            <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
              {["7d", "30d", "90d"].map((range) => (
                <button
                  key={range}
                  onClick={() => setTimeRange(range)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    timeRange === range
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>
          <div className="relative h-[220px]">
            {loading && chartHistory.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
                <Spinner className="h-8 w-8" />
                <span>Loading chart…</span>
              </div>
            ) : !loading && chartHistory.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t("dashboard.noDataYet")}
              </div>
            ) : (
              <>
                {loading && chartHistory.length === 0 && (
                  <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-card/80">
                    <Spinner className="h-8 w-8" />
                  </div>
                )}
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartHistory.length > 0 ? chartHistory : chartData}>
                    <defs>
                      <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.6} />
                    <XAxis dataKey="date" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} axisLine={{ stroke: "var(--border)" }} />
                    <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} axisLine={{ stroke: "var(--border)" }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "var(--card)",
                        borderColor: "var(--border)",
                        borderRadius: "8px",
                        color: "var(--card-foreground)",
                        fontSize: "12px",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="volume"
                      stroke="var(--chart-1)"
                      strokeWidth={2}
                      fill="url(#volumeGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </>
            )}
          </div>
        </div>

        {/* Interest Earned Chart */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-foreground">{t("dashboard.interestEarned")}</h3>
            <p className="text-xs text-muted-foreground">{t("dashboard.interestEarnedDesc")}</p>
          </div>
          <div className="relative h-[220px]">
            {loading && chartHistory.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
                <Spinner className="h-8 w-8" />
                <span>Loading chart…</span>
              </div>
            ) : !loading && chartHistory.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t("dashboard.noDataYet")}
              </div>
            ) : (
              <>
                {loading && chartHistory.length === 0 && (
                  <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-card/80">
                    <Spinner className="h-8 w-8" />
                  </div>
                )}
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartHistory.length > 0 ? chartHistory : chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.6} />
                    <XAxis dataKey="date" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} axisLine={{ stroke: "var(--border)" }} />
                    <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} axisLine={{ stroke: "var(--border)" }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "var(--card)",
                        borderColor: "var(--border)",
                        borderRadius: "8px",
                        color: "var(--card-foreground)",
                        fontSize: "12px",
                      }}
                    />
                    <Bar dataKey="interest" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Trading record (repaid funding trades from Bitfinex) */}
      {fundingTrades.length > 0 && (
        <div className="rounded-xl border border-border bg-card">
          <div className="border-b border-border p-5">
            <h3 className="text-sm font-semibold text-foreground">Trading record</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Repaid lending trades between registration and latest (Bitfinex funding trades). Sum of interest = Gross Profit above.
            </p>
          </div>
          <div className="overflow-x-auto max-h-[320px] overflow-y-auto">
            <table className="w-full text-left text-sm" role="table">
              <thead className="sticky top-0 bg-card border-b border-border z-10">
                <tr className="text-xs uppercase text-muted-foreground">
                  <th className="px-5 py-2.5 font-medium">Date</th>
                  <th className="px-5 py-2.5 font-medium">Currency</th>
                  <th className="px-5 py-2.5 font-medium text-right">Amount</th>
                  <th className="px-5 py-2.5 font-medium text-right">Rate</th>
                  <th className="px-5 py-2.5 font-medium text-right">Period (d)</th>
                  <th className="px-5 py-2.5 font-medium text-right">Interest (USD)</th>
                </tr>
              </thead>
              <tbody>
                {fundingTrades.slice(0, 100).map((t) => (
                  <tr key={t.id} className="border-b border-border/50 hover:bg-secondary/20">
                    <td className="px-5 py-2.5 text-muted-foreground">
                      {new Date(t.mts_create).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}
                    </td>
                    <td className="px-5 py-2.5 font-medium text-foreground">{t.currency}</td>
                    <td className="px-5 py-2.5 text-right font-mono">{t.amount.toFixed(4)}</td>
                    <td className="px-5 py-2.5 text-right font-mono">{(t.rate * 100).toFixed(2)}%</td>
                    <td className="px-5 py-2.5 text-right font-mono">{t.period}</td>
                    <td className="px-5 py-2.5 text-right font-mono text-primary">${t.interest_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {fundingTrades.length > 100 && (
            <p className="px-5 py-2 text-xs text-muted-foreground border-t border-border">
              Showing first 100 of {fundingTrades.length} trades.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
