"use client"

import { useEffect, useState } from "react"
import {
  DollarSign,
  TrendingUp,
  BarChart3,
  Clock,
  RefreshCw,
} from "lucide-react"
import { Spinner } from "@/components/ui/spinner"
import { useDateRange } from "@/lib/date-range-context"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { getBackendToken } from "@/lib/auth"
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

type TradeForChart = { mts_create: number; amount: number; interest_usd: number }

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
  const { range } = useDateRange()
  const [timeRange, setTimeRange] = useState("30d")
  const [grossProfit, setGrossProfit] = useState<number | null>(null)
  const [netProfit, setNetProfit] = useState<number | null>(null)
  const [chartHistory, setChartHistory] = useState<{ date: string; volume: number; interest: number }[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tokensRemaining, setTokensRemaining] = useState<number | null>(null)
  const [lendingDataSource, setLendingDataSource] = useState<"live" | "cache" | null>(null)
  const [lendingRateLimited, setLendingRateLimited] = useState(false)
  const [tradesCount, setTradesCount] = useState<number | null>(null)
  const [fundingTrades, setFundingTrades] = useState<Array<{ id: number; currency: string; mts_create: number; amount: number; rate: number; period: number; interest_usd: number }>>([])
  const [refreshing, setRefreshing] = useState(false)
  const [calculationBreakdown, setCalculationBreakdown] = useState<{
    trades_count: number
    per_currency: Array<{ currency: string; interest_ccy: number; ticker_price_usd: number; interest_usd: number }>
    total_gross_usd: number
    formula_note?: string
  } | null>(null)
  const [showBreakdown, setShowBreakdown] = useState(false)

  useEffect(() => {
    if (userId == null) {
      setGrossProfit(null)
      setNetProfit(null)
      setChartHistory([])
      setTokensRemaining(null)
      setLendingDataSource(null)
      setLendingRateLimited(false)
      setTradesCount(null)
      setFundingTrades([])
      setCalculationBreakdown(null)
      setLoading(false)
      return
    }
    const fetchStats = async () => {
      try {
        setLoading(true)
        setError(null)
        const token = await getBackendToken()
        const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}

        // Gross Profit and Net Profit: single direct backend source (server is source of truth)
        const lendingRes = await fetch(`${API_BACKEND}/stats/${userId}/lending`, { credentials: "include", headers })
        const src = lendingRes.headers.get("X-Data-Source")
        setLendingDataSource(src === "cache" ? "cache" : "live")
        setLendingRateLimited(lendingRes.headers.get("X-Rate-Limited") === "true")
        if (lendingRes.ok) {
          try {
            let lendingData: { gross_profit?: number; db_snapshot_gross?: number; net_profit?: number; trades?: unknown[]; total_trades_count?: number; calculation_breakdown?: unknown } | null = await lendingRes.json()
            // If normal response has zero gross profit, try persisted DB snapshot (works even when cache/API returned 0)
            if (typeof lendingData?.gross_profit === "number" && lendingData.gross_profit === 0) {
              const dbRes = await fetch(`${API_BACKEND}/stats/${userId}/lending?source=db`, { credentials: "include", headers })
              const dbData = dbRes.ok ? await dbRes.json() : null
              if (dbRes.ok && typeof dbData?.gross_profit === "number" && dbData.gross_profit > 0) {
                lendingData = dbData
                setLendingDataSource("db")
              }
            }
            // Use db_snapshot_gross when API returned 0 but sent snapshot (e.g. cache body had 0, backend merged db_snapshot_gross)
            let gross =
              typeof lendingData?.gross_profit === "number" && lendingData.gross_profit > 0
                ? lendingData.gross_profit
                : typeof lendingData?.db_snapshot_gross === "number" && (lendingData?.db_snapshot_gross ?? 0) > 0
                  ? (lendingData?.db_snapshot_gross ?? 0)
                  : 0
            let net =
              typeof lendingData?.net_profit === "number" && (lendingData?.net_profit ?? 0) > 0
                ? (lendingData?.net_profit ?? 0)
                : gross > 0
                  ? Math.round(gross * (1 - 0.15) * 100) / 100
                  : 0
            setGrossProfit(gross)
            setNetProfit(net)
            const trades = Array.isArray(lendingData?.trades) ? lendingData.trades : []
            setCalculationBreakdown(lendingData?.calculation_breakdown ?? null)
            let tradesForChart = trades as TradeForChart[]
            // When lending returns no trades but we have gross profit, fetch trades once for chart (cache/db path omits trades)
            if (tradesForChart.length === 0 && gross > 0) {
              try {
                const ftRes = await fetch(`${API_BACKEND}/api/funding-trades`, { credentials: "include", headers })
                if (ftRes.ok) {
                  const ftData = await ftRes.json()
                  tradesForChart = Array.isArray(ftData?.trades) ? (ftData.trades as TradeForChart[]) : []
                }
              } catch {
                // keep trades empty
              }
            }
            setFundingTrades(tradesForChart)
            setTradesCount(
              typeof lendingData?.total_trades_count === "number"
                ? lendingData.total_trades_count
                : tradesForChart.length
            )
            if (tradesForChart.length === 0) setChartHistory([])
            // else: chart derived in useEffect below when fundingTrades/timeRange change
          } catch (err) {
            setGrossProfit(0)
            setNetProfit(0)
            setFundingTrades([])
            setTradesCount(null)
            setCalculationBreakdown(null)
            setChartHistory([])
          }
        } else {
          setGrossProfit(0)
          setNetProfit(0)
          setFundingTrades([])
          setTradesCount(null)
          setCalculationBreakdown(null)
          setChartHistory([])
        }

        const statusRes = await fetch(`${API_BACKEND}/user-status/${userId}`, { credentials: "include", headers })
        if (statusRes.ok) {
          const statusData = await statusRes.json()
          const tr = statusData.tokens_remaining
          setTokensRemaining(typeof tr === "number" ? tr : null)
        }
      } catch (e) {
        const isNetworkError =
          (e instanceof TypeError && (e as Error).message === "Failed to fetch") ||
          (e instanceof Error && (e.message === "Failed to fetch" || e.message.includes("NetworkError")))
        setError(isNetworkError ? t("dashboard.apiUnreachable") : t("dashboard.unableToLoadProfit"))
        if (!isNetworkError) console.error("Failed to fetch stats", e)
        setChartHistory([])
      } finally {
        setLoading(false)
      }
    }

    fetchStats()
  }, [userId, range.start, range.end, timeRange, t])

  // Re-derive chart when user changes 7d/30d/90d (no refetch)
  useEffect(() => {
    if (userId == null || fundingTrades.length === 0) return
    const { start, end } = chartRangeFromTimeRange(timeRange)
    setChartHistory(deriveChartHistoryFromTrades(fundingTrades as TradeForChart[], start, end))
  }, [timeRange, userId, fundingTrades])

  const refreshFromServer = async () => {
    if (userId == null) return
    setRefreshing(true)
    try {
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/api/refresh-lending-stats`, { method: "POST", credentials: "include", headers })
      if (res.ok) {
        const data = await res.json()
        setGrossProfit(typeof data.gross_profit === "number" ? data.gross_profit : 0)
        setNetProfit(typeof data.net_profit === "number" ? data.net_profit : 0)
        const trades = Array.isArray(data.trades) ? data.trades : []
        setFundingTrades(trades)
        setTradesCount(typeof data.total_trades_count === "number" ? data.total_trades_count : trades.length)
        setCalculationBreakdown(data.calculation_breakdown ?? null)
        setLendingDataSource("live")
        const { start, end } = chartRangeFromTimeRange(timeRange)
        setChartHistory(deriveChartHistoryFromTrades(trades as TradeForChart[], start, end))
      }
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
          onClick={refreshFromServer}
          disabled={refreshing || loading}
          className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing…" : "Refresh Gross Profit"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Token credit – upfront so user sees balance before profit detail */}
      <div className="rounded-xl border border-emerald/20 bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald/10">
              <Clock className="h-5 w-5 text-emerald" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Token credit</p>
              <p className="text-xs text-muted-foreground">0.1 USD gross profit = 1 token used</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold text-emerald">
              {tokensRemaining !== null ? `${Math.round(tokensRemaining)} tokens remaining` : "—"}
            </span>
            <button
              onClick={() => onUpgradeClick?.()}
              className="rounded-lg bg-emerald px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-emerald/90 transition-colors"
            >
              {t("dashboard.upgradeToPro")}
            </button>
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
            <DollarSign className="h-4 w-4 text-emerald" />
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
                className="text-xs font-medium text-emerald hover:underline"
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
                          <td className="py-1 text-right font-mono text-emerald">${row.interest_usd.toFixed(4)}</td>
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
                    <td className="px-5 py-2.5 text-right font-mono text-emerald">${t.interest_usd.toFixed(4)}</td>
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
