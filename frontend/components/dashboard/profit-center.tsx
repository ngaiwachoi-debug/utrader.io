"use client"

import { useEffect, useState } from "react"
import {
  DollarSign,
  TrendingUp,
  Wallet,
  BarChart3,
  Clock,
} from "lucide-react"
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

const chartData = [
  { date: "02-19", volume: 12400, interest: 32 },
  { date: "02-20", volume: 18200, interest: 48 },
  { date: "02-21", volume: 22100, interest: 61 },
  { date: "02-22", volume: 15800, interest: 42 },
  { date: "02-23", volume: 24500, interest: 68 },
  { date: "02-24", volume: 19300, interest: 52 },
  { date: "02-25", volume: 21000, interest: 58 },
]

const lendingEngines = [
  {
    currency: "USD",
    status: "Active",
    rate: "2.63%",
    dailyChange: "-84.14%",
    amount: "$701,154,043",
    lent: "$45,200",
    earned: "$12.45",
    offers: 7,
  },
  {
    currency: "USDt",
    status: "Active",
    rate: "6.49%",
    dailyChange: "-58.08%",
    amount: "$74,105,449",
    lent: "$22,100",
    earned: "$8.32",
    offers: 4,
  },
  {
    currency: "APE",
    status: "Paused",
    rate: "67.35%",
    dailyChange: "-2.87%",
    amount: "$70,125",
    lent: "$0",
    earned: "$0.00",
    offers: 0,
  },
  {
    currency: "EGLD",
    status: "Active",
    rate: "49.27%",
    dailyChange: "+0.00%",
    amount: "$176",
    lent: "$176",
    earned: "$0.24",
    offers: 1,
  },
  {
    currency: "NEO",
    status: "Active",
    rate: "41.61%",
    dailyChange: "+18.51%",
    amount: "$2,746",
    lent: "$1,850",
    earned: "$2.11",
    offers: 2,
  },
  {
    currency: "SUI",
    status: "Active",
    rate: "30.84%",
    dailyChange: "+6.40%",
    amount: "$8,558",
    lent: "$5,200",
    earned: "$4.40",
    offers: 3,
  },
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
  const [lendingLimit, setLendingLimit] = useState<number>(250_000)
  const [lendingDataSource, setLendingDataSource] = useState<"live" | "cache" | null>(null)
  const [lendingRateLimited, setLendingRateLimited] = useState(false)
  const [tradesCount, setTradesCount] = useState<number | null>(null)
  const [fundingTrades, setFundingTrades] = useState<Array<{ id: number; currency: string; mts_create: number; amount: number; rate: number; period: number; interest_usd: number }>>([])
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
      setLendingLimit(250_000)
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
        // On dashboard load: force refresh gross profit from Bitfinex (returns repaid lending trades), then fetch stats
        try {
          const refreshRes = await fetch(`${API_BASE}/api/refresh-lending-stats`, { method: "POST", credentials: "include", headers })
          if (refreshRes.ok) {
            const refreshData = await refreshRes.json()
            const trades = refreshData.trades
            const arr = Array.isArray(trades) ? trades : []
            setTradesCount(arr.length)
            setFundingTrades(arr)
            if (refreshData.calculation_breakdown) {
              setCalculationBreakdown(refreshData.calculation_breakdown)
            } else {
              setCalculationBreakdown(null)
            }
          }
        } catch {
          // ignore refresh failure; we still load from cache/GET below
        }
        const start = range.start.toISOString().slice(0, 10)
        const end = range.end.toISOString().slice(0, 10)
        // Prefer lending stats (Bitfinex since registration); fallback to /stats
        const lendingRes = await fetch(`${API_BASE}/stats/${userId}/lending`)
        const src = lendingRes.headers.get("X-Data-Source")
        setLendingDataSource(src === "cache" ? "cache" : "live")
        setLendingRateLimited(lendingRes.headers.get("X-Rate-Limited") === "true")
        let gross = 0
        let net = 0
        if (lendingRes.ok) {
          const lendingData = await lendingRes.json()
          gross = lendingData.gross_profit ?? 0
          net = lendingData.net_profit ?? 0
        } else {
          const statsRes = await fetch(`${API_BASE}/stats/${userId}?start=${start}&end=${end}`)
          if (statsRes.ok) {
            const data = await statsRes.json()
            gross = data.gross_profit ?? 0
            net = data.net_profit ?? 0
          }
        }
        setGrossProfit(gross)
        setNetProfit(net)

        const [historyRes, statusRes] = await Promise.all([
          fetch(`${API_BASE}/stats/${userId}/history?start=${start}&end=${end}`, { credentials: "include", headers }),
          fetch(`${API_BASE}/user-status/${userId}`, { credentials: "include", headers }),
        ])
        if (historyRes.ok) {
          const history = await historyRes.json()
          setChartHistory(Array.isArray(history) ? history : [])
        } else {
          setChartHistory([])
        }
        if (statusRes.ok) {
          const statusData = await statusRes.json()
          const tr = statusData.tokens_remaining
          setTokensRemaining(typeof tr === "number" ? tr : null)
          setLendingLimit(Number(statusData.lending_limit) ?? 250_000)
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
  }, [userId, range.start, range.end, t])

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

  return (
    <div className="flex flex-col gap-6">
      {/* Page Title */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("dashboard.profitCenter")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("dashboard.profitCenterDesc")}
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

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
            <span className="text-2xl font-bold text-foreground">
              {loading && grossProfit === null ? "…" : `$${(grossProfit ?? 0).toFixed(2)}`}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {!loading && !error && (grossProfit ?? 0) === 0 ? t("dashboard.noDataYet") : t("dashboard.grossProfitSinceRegistration")}
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

        {/* Net Earnings */}
        <div className="rounded-xl border border-emerald/30 bg-emerald/5 p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-emerald">
              {t("dashboard.netEarnings")}
            </span>
            <Wallet className="h-4 w-4 text-emerald" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-emerald">
              {loading && netProfit === null ? "…" : `$${(netProfit ?? 0).toFixed(2)}`}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {!loading && !error && (netProfit ?? 0) === 0 ? t("dashboard.noDataYet") : t("dashboard.netProfitSinceRegistration")}
          </p>
        </div>
      </div>
      {(lendingDataSource === "cache" || lendingRateLimited) && (
        <p className="text-xs text-muted-foreground">
          {lendingRateLimited ? t("dashboard.rateLimited") : t("dashboard.dataCached")}
        </p>
      )}

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

      {/* Trial Countdown Bar */}
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
            <span className="text-xs text-muted-foreground">{t("header.lendingLimit")}: ${(lendingLimit ?? 0).toLocaleString()}</span>
            <button
              onClick={() => onUpgradeClick?.()}
              className="rounded-lg bg-emerald px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-emerald/90 transition-colors"
            >
              {t("dashboard.upgradeToPro")}
            </button>
          </div>
        </div>
      </div>

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
                      ? "bg-emerald text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>
          <div className="h-[220px]">
            {!loading && chartHistory.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t("dashboard.noDataYet")}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartHistory.length > 0 ? chartHistory : chartData}>
                  <defs>
                    <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={{ stroke: "#1e293b" }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={{ stroke: "#1e293b" }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f1729",
                      borderColor: "#1e293b",
                      borderRadius: "8px",
                      color: "#e2e8f0",
                      fontSize: "12px",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="volume"
                    stroke="#10b981"
                    strokeWidth={2}
                    fill="url(#volumeGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Interest Earned Chart */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-foreground">{t("dashboard.interestEarned")}</h3>
            <p className="text-xs text-muted-foreground">{t("dashboard.interestEarnedDesc")}</p>
          </div>
          <div className="h-[220px]">
            {!loading && chartHistory.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t("dashboard.noDataYet")}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartHistory.length > 0 ? chartHistory : chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={{ stroke: "#1e293b" }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={{ stroke: "#1e293b" }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0f1729",
                    borderColor: "#1e293b",
                    borderRadius: "8px",
                    color: "#e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="interest" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Active Lending Engines Table */}
      <div className="rounded-xl border border-border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5">
          <div>
            <h3 className="text-sm font-semibold text-foreground">Active Lending Engines</h3>
            <p className="text-xs text-muted-foreground">Market conditions and your active lending positions</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-emerald"></span>
              {lendingEngines.filter((e) => e.status === "Active").length} Active
            </span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-chart-2"></span>
              {lendingEngines.filter((e) => e.status === "Paused").length} Paused
            </span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" role="table">
            <thead>
              <tr className="border-b border-border text-xs uppercase text-muted-foreground">
                <th className="px-5 py-3 font-medium">Currency</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium text-right">Rate</th>
                <th className="hidden px-5 py-3 font-medium text-right md:table-cell">1d Change</th>
                <th className="hidden px-5 py-3 font-medium text-right lg:table-cell">Market Vol.</th>
                <th className="px-5 py-3 font-medium text-right">Lent</th>
                <th className="hidden px-5 py-3 font-medium text-right sm:table-cell">Earned</th>
                <th className="hidden px-5 py-3 font-medium text-right md:table-cell">Offers</th>
              </tr>
            </thead>
            <tbody>
              {lendingEngines.map((engine) => (
                <tr
                  key={engine.currency}
                  className="border-b border-border/50 transition-colors hover:bg-secondary/30"
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary text-xs font-bold text-foreground">
                        {engine.currency.charAt(0)}
                      </div>
                      <span className="font-medium text-foreground">{engine.currency}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        engine.status === "Active"
                          ? "bg-emerald/10 text-emerald"
                          : "bg-chart-2/10 text-chart-2"
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          engine.status === "Active" ? "bg-emerald" : "bg-chart-2"
                        }`}
                      ></span>
                      {engine.status}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono text-foreground">{engine.rate}</td>
                  <td
                    className={`hidden px-5 py-3.5 text-right font-mono md:table-cell ${
                      engine.dailyChange.startsWith("+")
                        ? "text-emerald"
                        : "text-destructive"
                    }`}
                  >
                    {engine.dailyChange}
                  </td>
                  <td className="hidden px-5 py-3.5 text-right font-mono text-muted-foreground lg:table-cell">
                    {engine.amount}
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono text-foreground">{engine.lent}</td>
                  <td className="hidden px-5 py-3.5 text-right font-mono text-emerald sm:table-cell">
                    {engine.earned}
                  </td>
                  <td className="hidden px-5 py-3.5 text-right font-mono text-muted-foreground md:table-cell">
                    {engine.offers}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
