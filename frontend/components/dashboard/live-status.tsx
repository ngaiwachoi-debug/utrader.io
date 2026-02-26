"use client"

import { useEffect, useState } from "react"
import {
  Wallet,
  DollarSign,
  TrendingUp,
  ArrowUpRight,
  RefreshCw,
  BarChart3,
  PieChart,
  Activity,
  Clock,
  Moon,
} from "lucide-react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

const hourlyData = [
  { time: "00:00", usdVolume: 12000, usdRate: 2.3, usdtVolume: 8000, usdtRate: 5.2 },
  { time: "02:00", usdVolume: 8000, usdRate: 2.1, usdtVolume: 15000, usdtRate: 6.1 },
  { time: "04:00", usdVolume: 22000, usdRate: 2.6, usdtVolume: 18000, usdtRate: 7.3 },
  { time: "06:00", usdVolume: 15000, usdRate: 2.4, usdtVolume: 12000, usdtRate: 5.8 },
  { time: "08:00", usdVolume: 18000, usdRate: 2.8, usdtVolume: 20000, usdtRate: 8.2 },
  { time: "10:00", usdVolume: 24000, usdRate: 3.1, usdtVolume: 16000, usdtRate: 6.5 },
  { time: "12:00", usdVolume: 20000, usdRate: 2.9, usdtVolume: 22000, usdtRate: 7.8 },
  { time: "14:00", usdVolume: 16000, usdRate: 2.5, usdtVolume: 14000, usdtRate: 6.2 },
  { time: "16:00", usdVolume: 21000, usdRate: 2.7, usdtVolume: 19000, usdtRate: 7.1 },
  { time: "18:00", usdVolume: 14000, usdRate: 2.2, usdtVolume: 11000, usdtRate: 5.5 },
  { time: "20:00", usdVolume: 19000, usdRate: 2.6, usdtVolume: 17000, usdtRate: 6.9 },
  { time: "22:00", usdVolume: 17000, usdRate: 2.4, usdtVolume: 13000, usdtRate: 6.0 },
]

const marketData = [
  { currency: "USD", rate: "2.63%", dailyChange: "-84.14%", volume: "$701,154,043" },
  { currency: "USDt", rate: "6.49%", dailyChange: "-58.08%", volume: "$74,105,449" },
  { currency: "APE", rate: "67.35%", dailyChange: "-2.87%", volume: "$70,125" },
  { currency: "EGLD", rate: "49.27%", dailyChange: "+0.00%", volume: "$176" },
  { currency: "NEO", rate: "41.61%", dailyChange: "+18.51%", volume: "$2,746" },
  { currency: "APT", rate: "35.76%", dailyChange: "+0.30%", volume: "$125" },
  { currency: "ATOM", rate: "34.22%", dailyChange: "-18.37%", volume: "$884" },
  { currency: "SUI", rate: "30.84%", dailyChange: "+6.40%", volume: "$8,558" },
  { currency: "FIL", rate: "28.81%", dailyChange: "-5.33%", volume: "$8,632" },
  { currency: "SUSHI", rate: "22.63%", dailyChange: "+106.67%", volume: "$3,015" },
]

type LendingLedgerRow = {
  time: string
  rateRange: string
  maxDays: number
  cumulative: string
  rate: string
  amount: string
  count: number
  total: string
}

type WalletSummary = {
  total_usd_all: number
  usd_only: number
  per_currency: Record<string, number>
  per_currency_usd: Record<string, number>
  lent_per_currency?: Record<string, number>
  total_lent_usd?: number
}

export function LiveStatus() {
  const t = useT()
  const userId = useCurrentUserId()
  const [activeTab, setActiveTab] = useState("total")
  const [totalAssets, setTotalAssets] = useState<number | null>(null)
  const [walletSummary, setWalletSummary] = useState<WalletSummary | null>(null)
  const [walletError, setWalletError] = useState<string | null>(null)
  const [botActive, setBotActive] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [walletDataSource, setWalletDataSource] = useState<"live" | "cache" | null>(null)
  const [walletRateLimited, setWalletRateLimited] = useState(false)
  const [refreshCooldownUntil, setRefreshCooldownUntil] = useState(0)
  const [refreshCooldownSec, setRefreshCooldownSec] = useState(0)
  const REFRESH_COOLDOWN_SEC = 15
  const [ledgerCurrentRate, setLedgerCurrentRate] = useState<string | null>(null)
  const [ledgerDailyRate, setLedgerDailyRate] = useState<number | null>(null)
  const [ledgerRows, setLedgerRows] = useState<LendingLedgerRow[]>([])
  const [ledgerLoading, setLedgerLoading] = useState(false)
  const [ledgerError, setLedgerError] = useState<string | null>(null)

  useEffect(() => {
    const interval = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((refreshCooldownUntil - Date.now()) / 1000))
      setRefreshCooldownSec(remaining)
    }, 1000)
    return () => clearInterval(interval)
  }, [refreshCooldownUntil])

  const fetchLedger = async () => {
    try {
      setLedgerLoading(true)
      setLedgerError(null)
      const res = await fetch(`${API_BASE}/api/funding-ledger?symbol=fUSD`)
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.rows) {
        setLedgerCurrentRate(data.currentRate ?? null)
        setLedgerDailyRate(typeof data.dailyRate === "number" ? data.dailyRate : null)
        setLedgerRows(Array.isArray(data.rows) ? data.rows : [])
      } else {
        setLedgerCurrentRate(null)
        setLedgerDailyRate(null)
        setLedgerRows([])
        setLedgerError(data.error || "Failed to load ledger")
      }
    } catch (e) {
      setLedgerError("Failed to load ledger")
      setLedgerRows([])
      setLedgerCurrentRate(null)
      setLedgerDailyRate(null)
    } finally {
      setLedgerLoading(false)
    }
  }

  const refreshStatus = async () => {
    if (userId == null) return
    try {
      setLoading(true)
      setError(null)
      setWalletError(null)
      const [botRes, walletsRes] = await Promise.all([
        fetch(`${API_BASE}/bot-stats/${userId}`),
        fetch(`${API_BASE}/wallets/${userId}`),
      ])
      if (botRes.ok) {
        const data = await botRes.json()
        setBotActive(Boolean(data.active))
        const total = parseFloat(String(data.total_loaned ?? "0").replace(/,/g, ""))
        setTotalAssets(Number.isFinite(total) ? total : 0)
      }
      if (walletsRes.ok) {
        const wallets = await walletsRes.json()
        setWalletSummary({
          total_usd_all: Number(wallets.total_usd_all) || 0,
          usd_only: Number(wallets.usd_only) || 0,
          per_currency: wallets.per_currency || {},
          per_currency_usd: wallets.per_currency_usd || {},
          lent_per_currency: wallets.lent_per_currency || {},
          total_lent_usd: Number(wallets.total_lent_usd) ?? 0,
        })
        const src = walletsRes.headers.get("X-Data-Source")
        setWalletDataSource(src === "cache" ? "cache" : "live")
        setWalletRateLimited(walletsRes.headers.get("X-Rate-Limited") === "true")
        setWalletError(null)
      } else {
        setWalletError(t("liveStatus.connectApiKeys"))
      }
      setRefreshCooldownUntil(Date.now() + REFRESH_COOLDOWN_SEC * 1000)
      await fetchLedger()
    } catch (e) {
      console.error("Failed to fetch live status", e)
      setError(t("liveStatus.unableToLoad"))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (userId == null) {
      setTotalAssets(null)
      setWalletSummary(null)
      setWalletError(null)
      setBotActive(null)
      return
    }
    refreshStatus()
  }, [userId])

  useEffect(() => {
    fetchLedger()
  }, [])

  const handleStart = async () => {
    if (userId == null) return
    try {
      setIsStarting(true)
      const res = await fetch(`${API_BASE}/start-bot/${userId}`, { method: "POST" })
      if (!res.ok) {
        console.error("Start bot failed", await res.text())
      }
      await refreshStatus()
    } finally {
      setIsStarting(false)
    }
  }

  const handleStop = async () => {
    if (userId == null) return
    try {
      setIsStopping(true)
      const res = await fetch(`${API_BASE}/stop-bot/${userId}`, { method: "POST" })
      if (!res.ok) {
        console.error("Stop bot failed", await res.text())
      }
      await refreshStatus()
    } finally {
      setIsStopping(false)
    }
  }

  if (userId == null) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold text-foreground">{t("liveStatus.title")}</h1>
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted-foreground">{t("liveStatus.connectApiKeys")}</p>
          <p className="mt-2 text-sm text-muted-foreground">Sign in to see your lending data.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Page Title */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-emerald">February 25, 2026</p>
          <h1 className="text-2xl font-bold text-foreground">{t("liveStatus.title")}</h1>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${
              botActive ? "bg-emerald/10 text-emerald" : "bg-destructive/10 text-destructive"
            }`}
          >
            {botActive === null ? t("liveStatus.statusUnknown") : botActive ? t("liveStatus.botActive") : t("liveStatus.botStopped")}
          </span>
          <button
            onClick={refreshStatus}
            disabled={loading || refreshCooldownSec > 0}
            className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground hover:border-emerald/50 hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            title={refreshCooldownSec > 0 ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : undefined}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            {refreshCooldownSec > 0 ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : t("liveStatus.refresh")}
          </button>
          <button
            onClick={handleStart}
            disabled={isStarting}
            className="rounded-lg bg-emerald px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-emerald-dark disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {isStarting ? t("liveStatus.starting") : t("liveStatus.startBot")}
          </button>
          <button
            onClick={handleStop}
            disabled={isStopping}
            className="rounded-lg bg-destructive px-3 py-2 text-xs font-semibold text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {isStopping ? t("liveStatus.stopping") : t("liveStatus.stopBot")}
          </button>
        </div>
      </div>

      {/* Tab */}
      <div>
        <button
          className="rounded-full bg-emerald px-4 py-1.5 text-xs font-semibold text-primary-foreground"
        >
          {t("liveStatus.total")}
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Client assets (Bitfinex total) */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-emerald/10 px-2 py-0.5 text-xs font-semibold text-emerald">{t("liveStatus.assets")}</span>
              <span className="text-xs text-muted-foreground">{t("liveStatus.allCurrencies")}</span>
            </div>
            <Wallet className="h-5 w-5 text-emerald" />
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold text-foreground">
              {loading && walletSummary === null && !walletError ? "…" : walletError ? "—" : `$${(walletSummary?.total_usd_all ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {walletError ?? (walletSummary ? t("liveStatus.totalUsdValue") : t("liveStatus.loading"))}
            {walletDataSource === "cache" && !walletError && (
              <span className="ml-1 text-muted-foreground"> · {t("liveStatus.dataCached")}</span>
            )}
            {walletRateLimited && (
              <span className="ml-1 text-amber-600 dark:text-amber-400" title={t("liveStatus.rateLimited")}> · ⚠ {t("liveStatus.rateLimited")}</span>
            )}
          </p>
        </div>

        {/* Currently loaned (Bitfinex total_lent_usd when available, else bot total) */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-destructive/10 px-2 py-0.5 text-xs font-semibold text-destructive">{t("liveStatus.loaned")}</span>
              <span className="text-xs text-muted-foreground">{t("liveStatus.currentlyLoaned")}</span>
            </div>
            <DollarSign className="h-5 w-5 text-emerald" />
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold text-foreground">
              {loading && walletSummary == null && totalAssets === null ? "…" : `$${(walletSummary?.total_lent_usd ?? totalAssets ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {botActive ? "Bot is actively deploying lending capital." : "Bot is currently idle."}
          </p>
        </div>
      </div>

      {/* Currently Lent Out per currency (from Bitfinex) */}
      {walletSummary?.lent_per_currency && Object.keys(walletSummary.lent_per_currency).length > 0 && (
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">{t("liveStatus.currentlyLentOut")}</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs" role="table">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Currency</th>
                  <th className="py-2 text-right font-medium">Amount lent</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(walletSummary.lent_per_currency)
                  .filter(([, amount]) => Number(amount) !== 0)
                  .map(([currency, amount]) => (
                    <tr key={currency} className="border-b border-border/50">
                      <td className="py-2.5 pr-4 font-medium text-foreground">{currency}</td>
                      <td className="py-2.5 text-right font-mono text-foreground">
                        {Number(amount).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Portfolio Allocation (after currency lend out) */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <PieChart className="h-5 w-5 text-emerald" />
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.portfolioAllocation")}</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{t("liveStatus.capitalDeploymentOverview")}</p>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <span className="text-xl font-bold text-emerald">
            ${(walletSummary?.total_usd_all ?? totalAssets ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className="text-xs text-muted-foreground">100.0% Active</span>
          <span className="text-xs text-muted-foreground">100.0% deployed</span>
        </div>
        <div className="mb-4">
          <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
            <span>{t("liveStatus.allocationBreakdown")}</span>
          </div>
          <div className="h-3 w-full rounded-full bg-secondary overflow-hidden flex">
            <div
              className="h-full bg-emerald transition-all"
              style={{
                width: `${(() => {
                  const lent = walletSummary?.total_lent_usd ?? totalAssets ?? 0
                  const total = walletSummary?.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, (100 * lent) / total) : 0
                })()}%`,
              }}
            />
            <div
              className="h-full bg-amber-500/80 transition-all"
              style={{
                width: `${(() => {
                  const lent = walletSummary?.total_lent_usd ?? totalAssets ?? 0
                  const total = walletSummary?.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, Math.max(0, (100 * (total - lent)) / total)) : total ? 100 : 0
                })()}%`,
              }}
            />
          </div>
          <div className="flex gap-4 mt-1.5 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-emerald" />
              {t("liveStatus.earning")}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-amber-500/80" />
              {t("liveStatus.deploying")}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-emerald/30 bg-emerald/5 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.activelyEarning")}</span>
              <Activity className="h-4 w-4 text-emerald" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              ${(walletSummary?.total_lent_usd ?? totalAssets ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-emerald">
              {walletSummary?.total_usd_all && walletSummary.total_usd_all > 0
                ? `${(((walletSummary?.total_lent_usd ?? totalAssets ?? 0) / walletSummary.total_usd_all) * 100).toFixed(1)}%`
                : "0.0%"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.generatingReturns")}</p>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.pendingDeployment")}</span>
              <Clock className="h-4 w-4 text-amber-500" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              ${((walletSummary?.total_usd_all ?? 0) - (walletSummary?.total_lent_usd ?? totalAssets ?? 0)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-amber-500">
              {walletSummary?.total_usd_all && walletSummary.total_usd_all > 0
                ? `${((((walletSummary.total_usd_all - (walletSummary?.total_lent_usd ?? totalAssets ?? 0)) / walletSummary.total_usd_all) * 100)).toFixed(1)}%`
                : "0.0%"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.awaitingOpportunities")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/30 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.idleFunds")}</span>
              <Moon className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">$0.00</p>
            <p className="text-xs text-muted-foreground">0.0%</p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.notDeployed")}</p>
          </div>
        </div>
      </div>

      {/* Performance (key metrics) */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="h-5 w-5 text-amber-500" />
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.performance")}</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{t("liveStatus.keyMetrics")}</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-border bg-secondary/20 p-4">
            <p className="text-xs font-medium text-muted-foreground">{t("liveStatus.estDailyEarnings")}</p>
            <p className="mt-2 text-xl font-bold text-emerald">$44.03</p>
            <p className="text-xs text-muted-foreground">{t("liveStatus.basedOnCurrentRates")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/20 p-4">
            <p className="text-xs font-medium text-muted-foreground">{t("liveStatus.weightedAvgApr")}</p>
            <p className="mt-2 text-xl font-bold text-blue-400">14.34%</p>
            <p className="text-xs text-muted-foreground">{t("liveStatus.acrossAllActiveLending")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/20 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.activeOrders")}</span>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">54</p>
            <p className="text-xs text-muted-foreground">{t("liveStatus.pendingExecution")}</p>
          </div>
        </div>
      </div>

      {/* 24h Lending Chart */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-foreground">24h Lending Record</h3>
          <p className="text-xs text-muted-foreground">{t("liveStatus.realtimeLending")}</p>
        </div>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" tick={{ fill: "#94a3b8", fontSize: 10 }} axisLine={{ stroke: "#1e293b" }} />
              <YAxis yAxisId="left" tick={{ fill: "#94a3b8", fontSize: 10 }} axisLine={{ stroke: "#1e293b" }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#94a3b8", fontSize: 10 }} axisLine={{ stroke: "#1e293b" }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f1729",
                  borderColor: "#1e293b",
                  borderRadius: "8px",
                  color: "#e2e8f0",
                  fontSize: "12px",
                }}
              />
              <Line yAxisId="left" type="monotone" dataKey="usdVolume" stroke="#10b981" strokeWidth={2} dot={false} name="USD Volume" />
              <Line yAxisId="left" type="monotone" dataKey="usdtVolume" stroke="#ef4444" strokeWidth={2} dot={false} name="USDt Volume" />
              <Bar yAxisId="right" dataKey="usdRate" fill="#10b981" opacity={0.3} name="USD Rate %" />
              <Bar yAxisId="right" dataKey="usdtRate" fill="#ef4444" opacity={0.3} name="USDt Rate %" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-6 rounded-full bg-emerald"></span>
            USD Volume
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-6 rounded-full bg-destructive"></span>
            USDt Volume
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-6 rounded-full bg-emerald/30"></span>
            USD Rate
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-6 rounded-full bg-destructive/30"></span>
            USDt Rate
          </span>
        </div>
      </div>

      {/* Lending Ledger Table */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border p-5">
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.bitfinexLendingLedger")}</h3>
          <p className="text-xs text-muted-foreground">{t("liveStatus.lendingLedgerDesc")}</p>
        </div>

        {/* Current Rate Card — from Bitfinex funding stats */}
        <div className="m-5 rounded-xl bg-emerald/10 border border-emerald/20 p-5">
          <p className="text-xs text-muted-foreground">{t("liveStatus.currentAnnualRate")}</p>
          <p className="text-3xl font-bold text-emerald mt-1">
            {ledgerLoading ? "…" : ledgerCurrentRate ?? "—"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {t("liveStatus.dailyRate")} {ledgerLoading ? "…" : ledgerDailyRate != null ? ledgerDailyRate.toFixed(6) : "—"}
          </p>
        </div>

        {ledgerError && (
          <p className="mx-5 mb-2 text-xs text-amber-600 dark:text-amber-400">{ledgerError}</p>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs" role="table">
            <thead>
              <tr className="border-b border-border text-xs uppercase text-muted-foreground">
                <th className="px-5 py-3 font-medium">{t("liveStatus.time")}</th>
                <th className="px-5 py-3 font-medium">{t("liveStatus.rateRange")}</th>
                <th className="hidden px-5 py-3 font-medium text-right sm:table-cell">{t("liveStatus.maxDays")}</th>
                <th className="hidden px-5 py-3 font-medium text-right md:table-cell">{t("liveStatus.cumulative")}</th>
                <th className="px-5 py-3 font-medium text-right">{t("liveStatus.rate")}</th>
                <th className="hidden px-5 py-3 font-medium text-right lg:table-cell">{t("liveStatus.amount")}</th>
                <th className="hidden px-5 py-3 font-medium text-right sm:table-cell">{t("liveStatus.count")}</th>
                <th className="px-5 py-3 font-medium text-right">{t("liveStatus.totalCol")}</th>
              </tr>
            </thead>
            <tbody>
              {ledgerRows.length === 0 && !ledgerLoading && (
                <tr>
                  <td colSpan={8} className="px-5 py-6 text-center text-muted-foreground">
                    {ledgerError ? ledgerError : t("dashboard.noDataYet")}
                  </td>
                </tr>
              )}
              {ledgerRows.map((row, i) => (
                <tr key={i} className="border-b border-border/50 transition-colors hover:bg-secondary/30">
                  <td className="px-5 py-3 font-mono text-foreground">{row.time}</td>
                  <td className="px-5 py-3 font-mono text-muted-foreground">{row.rateRange}</td>
                  <td className="hidden px-5 py-3 text-right font-mono text-muted-foreground sm:table-cell">{row.maxDays}</td>
                  <td className="hidden px-5 py-3 text-right font-mono text-muted-foreground md:table-cell">{row.cumulative}</td>
                  <td className="px-5 py-3 text-right font-bold font-mono text-emerald">{row.rate}</td>
                  <td className="hidden px-5 py-3 text-right font-mono text-muted-foreground lg:table-cell">{row.amount}</td>
                  <td className="hidden px-5 py-3 text-right font-mono text-muted-foreground sm:table-cell">{row.count}</td>
                  <td className="px-5 py-3 text-right font-mono text-foreground">{row.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
