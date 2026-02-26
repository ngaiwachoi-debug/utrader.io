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
import { getBackendToken } from "@/lib/auth"
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

type CreditDetail = { id: number; symbol: string; amount: number; rate: number; period: number; amount_usd: number }

type WalletSummary = {
  total_usd_all: number
  usd_only: number
  per_currency: Record<string, number>
  per_currency_usd: Record<string, number>
  lent_per_currency?: Record<string, number>
  offers_per_currency?: Record<string, number>
  lent_per_currency_usd?: Record<string, number>
  offers_per_currency_usd?: Record<string, number>
  idle_per_currency_usd?: Record<string, number>
  total_lent_usd?: number
  total_offers_usd?: number
  idle_usd?: number
  weighted_avg_apr_pct?: number
  est_daily_earnings_usd?: number
  yield_over_total_pct?: number
  credits_count?: number
  offers_count?: number
  credits_detail?: CreditDetail[]
  offers_detail?: CreditDetail[]
}

/** Client-side cache for Live Status: 10 minutes. No reload except on Refresh click. */
const LIVE_STATUS_CACHE_TTL_MS = 10 * 60 * 1000
type LiveStatusCacheEntry = {
  fetchedAt: number
  botActive: boolean | null
  totalAssets: number | null
  walletSummary: WalletSummary | null
  walletError: string | null
  walletDataSource: "live" | "cache" | null
  walletRateLimited: boolean
}
const liveStatusCache: Record<number, LiveStatusCacheEntry> = {}

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
  const [ledgerPage, setLedgerPage] = useState(1)

  useEffect(() => {
    const interval = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((refreshCooldownUntil - Date.now()) / 1000))
      setRefreshCooldownSec(remaining)
    }, 1000)
    return () => clearInterval(interval)
  }, [refreshCooldownUntil])

  useEffect(() => {
    const len = walletSummary?.credits_detail?.length ?? 0
    if (len > 0) setLedgerPage(1)
  }, [walletSummary?.credits_detail?.length])

  const refreshStatus = async () => {
    if (userId == null) return
    try {
      setLoading(true)
      setError(null)
      setWalletError(null)
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const [botRes, walletsRes] = await Promise.all([
        fetch(`${API_BASE}/bot-stats/${userId}`, { credentials: "include", headers }),
        fetch(`${API_BASE}/wallets/${userId}`, { credentials: "include", headers }),
      ])
      let nextBotActive: boolean | null = null
      let nextTotalAssets: number | null = null
      let nextWalletSummary: WalletSummary | null = walletSummary
      let nextWalletError: string | null = null
      let nextWalletDataSource: "live" | "cache" | null = null
      let nextWalletRateLimited = false

      if (botRes.ok) {
        const data = await botRes.json()
        nextBotActive = Boolean(data.active)
        const total = parseFloat(String(data.total_loaned ?? "0").replace(/,/g, ""))
        nextTotalAssets = Number.isFinite(total) ? total : 0
      }
      if (walletsRes.ok) {
        const wallets = await walletsRes.json()
        nextWalletSummary = {
          total_usd_all: Number(wallets.total_usd_all) || 0,
          usd_only: Number(wallets.usd_only) || 0,
          per_currency: wallets.per_currency || {},
          per_currency_usd: wallets.per_currency_usd || {},
          lent_per_currency: wallets.lent_per_currency || {},
          offers_per_currency: wallets.offers_per_currency || {},
          lent_per_currency_usd: wallets.lent_per_currency_usd || {},
          offers_per_currency_usd: wallets.offers_per_currency_usd || {},
          idle_per_currency_usd: wallets.idle_per_currency_usd || {},
          total_lent_usd: Number(wallets.total_lent_usd) ?? 0,
          total_offers_usd: Number(wallets.total_offers_usd) ?? 0,
          idle_usd: Number(wallets.idle_usd) ?? 0,
          weighted_avg_apr_pct: Number(wallets.weighted_avg_apr_pct) ?? 0,
          est_daily_earnings_usd: Number(wallets.est_daily_earnings_usd) ?? 0,
          yield_over_total_pct: Number(wallets.yield_over_total_pct) ?? 0,
          credits_count: Number(wallets.credits_count) ?? 0,
          offers_count: Number(wallets.offers_count) ?? 0,
          credits_detail: Array.isArray(wallets.credits_detail) ? wallets.credits_detail : [],
          offers_detail: Array.isArray(wallets.offers_detail) ? wallets.offers_detail : [],
        }
        nextWalletDataSource = walletsRes.headers.get("X-Data-Source") === "cache" ? "cache" : "live"
        nextWalletRateLimited = walletsRes.headers.get("X-Rate-Limited") === "true"
      } else {
        const incomplete = walletsRes.headers.get("X-Data-Incomplete") === "true"
        nextWalletError =
          walletsRes.status === 503 || incomplete
            ? t("liveStatus.dataIncomplete")
            : t("liveStatus.connectApiKeys")
      }

      setBotActive(nextBotActive)
      setTotalAssets(nextTotalAssets)
      setWalletSummary(nextWalletSummary)
      setWalletError(nextWalletError)
      setWalletDataSource(nextWalletDataSource)
      setWalletRateLimited(nextWalletRateLimited)
      setRefreshCooldownUntil(Date.now() + REFRESH_COOLDOWN_SEC * 1000)

      liveStatusCache[userId] = {
        fetchedAt: Date.now(),
        botActive: nextBotActive,
        totalAssets: nextTotalAssets,
        walletSummary: nextWalletSummary,
        walletError: nextWalletError,
        walletDataSource: nextWalletDataSource,
        walletRateLimited: nextWalletRateLimited,
      }
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
      setWalletDataSource(null)
      setWalletRateLimited(false)
      return
    }
    const cached = liveStatusCache[userId]
    if (cached && Date.now() - cached.fetchedAt < LIVE_STATUS_CACHE_TTL_MS) {
      setBotActive(cached.botActive)
      setTotalAssets(cached.totalAssets)
      setWalletSummary(cached.walletSummary)
      setWalletError(cached.walletError)
      setWalletDataSource(cached.walletDataSource)
      setWalletRateLimited(cached.walletRateLimited)
      setLoading(false)
      return
    }
    refreshStatus()
  }, [userId])

  // Poll bot status every 5s so Running/Stopped updates without full refresh
  const BOT_STATUS_POLL_MS = 5000
  useEffect(() => {
    if (userId == null) return
    const pollBotStatus = async () => {
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      fetch(`${API_BASE}/bot-stats/${userId}`, { credentials: "include", headers })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data && typeof data.active === "boolean") setBotActive(data.active)
        })
        .catch(() => {})
    }
    const t = setInterval(pollBotStatus, BOT_STATUS_POLL_MS)
    return () => clearInterval(t)
  }, [userId])


  const handleStart = async () => {
    if (userId == null) return
    try {
      setIsStarting(true)
      setError(null)
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BASE}/start-bot`, {
        method: "POST",
        credentials: "include",
        headers,
      })
      if (!res.ok) {
        const text = await res.text()
        let msg: string
        try {
          const j = JSON.parse(text)
          msg = j.detail || text
        } catch {
          msg = text || t("liveStatus.startFailed")
        }
        setError(msg || t("liveStatus.startFailed"))
      }
      await refreshStatus()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      const isNetworkError = msg === "Failed to fetch" || msg.includes("NetworkError")
      setError(isNetworkError ? t("dashboard.apiUnreachable") : msg)
    } finally {
      setIsStarting(false)
    }
  }

  const handleStop = async () => {
    if (userId == null) return
    try {
      setIsStopping(true)
      setError(null)
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BASE}/stop-bot`, {
        method: "POST",
        credentials: "include",
        headers,
      })
      if (!res.ok) {
        const text = await res.text()
        try {
          const j = JSON.parse(text)
          setError(j.detail || text)
        } catch {
          setError(text || "Stop failed")
        }
      }
      await refreshStatus()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      const isNetworkError = msg === "Failed to fetch" || msg.includes("NetworkError")
      setError(isNetworkError ? t("dashboard.apiUnreachable") : msg)
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
          {!botActive && (
            <button
              onClick={handleStart}
              disabled={isStarting}
              className="rounded-lg bg-emerald px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-emerald/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            >
              {isStarting ? t("liveStatus.starting") : t("liveStatus.startBot")}
            </button>
          )}
          {botActive && (
            <button
              onClick={handleStop}
              disabled={isStopping}
              className="rounded-lg bg-destructive px-3 py-2 text-xs font-semibold text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            >
              {isStopping ? t("liveStatus.stopping") : t("liveStatus.stopBot")}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

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
              {!walletSummary ? (loading ? "…" : "—") : `$${(walletSummary.total_usd_all ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {walletError ?? (walletSummary ? t("liveStatus.totalUsdValue") : loading ? t("liveStatus.loading") : "—")}
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
              {!walletSummary ? (loading ? "…" : "—") : `$${(walletSummary.total_lent_usd ?? totalAssets ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {botActive ? "Bot is actively deploying lending capital." : "Bot is currently idle."}
          </p>
        </div>
      </div>

      {/* Currently Lent Out: bar per currency (Amount lent | Pending | Idle); hide if total USD < 1 (incl. BTC, ETH, XRP) */}
      {walletSummary && (() => {
        const lentUsd = walletSummary.lent_per_currency_usd ?? {}
        const offersUsd = walletSummary.offers_per_currency_usd ?? {}
        const idleUsd = walletSummary.idle_per_currency_usd ?? {}
        const MIN_DISPLAY_USD = 1
        const currencies = Array.from(new Set([
          ...Object.keys(walletSummary.per_currency_usd ?? {}),
          ...Object.keys(lentUsd),
          ...Object.keys(offersUsd),
        ]))
          .filter((c) => {
            const total = (lentUsd[c] ?? 0) + (offersUsd[c] ?? 0) + (idleUsd[c] ?? 0)
            return total >= MIN_DISPLAY_USD
          })
          .sort()
        if (currencies.length === 0) return null
        return (
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3">{t("liveStatus.currentlyLentOut")}</h3>
            <p className="text-xs text-muted-foreground mb-4">{t("liveStatus.capitalDeploymentOverview")}</p>
            <div className="space-y-4">
              {currencies.map((currency) => {
                const lent = lentUsd[currency] ?? 0
                const offers = offersUsd[currency] ?? 0
                const idle = idleUsd[currency] ?? 0
                const total = lent + offers + idle
                const pct = (v: number) => (total > 0 ? (100 * v) / total : 0)
                return (
                  <div key={currency} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-foreground">{currency}</span>
                      <span className="text-muted-foreground">
                        ${total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} total
                      </span>
                    </div>
                    <div className="h-3 w-full rounded-full bg-secondary overflow-hidden flex">
                      <div
                        className="h-full bg-emerald transition-all"
                        style={{ width: `${Math.min(100, pct(lent))}%` }}
                        title={`Amount lent: $${lent.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                      />
                      <div
                        className="h-full bg-amber-500/80 transition-all"
                        style={{ width: `${Math.min(100, pct(offers))}%` }}
                        title={`Pending: $${offers.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                      />
                      <div
                        className="h-full bg-muted-foreground/50 transition-all"
                        style={{ width: `${Math.min(100, pct(idle))}%` }}
                        title={`Idle: $${idle.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                      />
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        <span className="h-1.5 w-3 rounded-full bg-emerald" />
                        {t("liveStatus.earning")}: ${lent.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-1.5 w-3 rounded-full bg-amber-500/80" />
                        {t("liveStatus.inOrderBook")}: ${offers.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-1.5 w-3 rounded-full bg-muted-foreground/50" />
                        {t("liveStatus.idleFunds")}: ${idle.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })()}

      {/* Portfolio Allocation (after currency lend out) */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <PieChart className="h-5 w-5 text-emerald" />
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.portfolioAllocation")}</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{t("liveStatus.capitalDeploymentOverview")}</p>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <span className="text-xl font-bold text-emerald">
            {!walletSummary ? (loading ? "…" : "—") : `$${(walletSummary.total_usd_all ?? totalAssets ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          </span>
          <span className="text-xs text-muted-foreground">{walletSummary ? "100.0% Active" : "—"}</span>
          <span className="text-xs text-muted-foreground">{walletSummary ? "100.0% deployed" : "—"}</span>
        </div>
        <div className="mb-4">
          <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
            <span>{t("liveStatus.allocationBreakdown")}</span>
          </div>
          <div className="h-3 w-full rounded-full bg-secondary overflow-hidden flex">
            <div
              className="h-full bg-emerald transition-all"
              style={{
                width: `${!walletSummary ? 0 : (() => {
                  const lent = walletSummary.total_lent_usd ?? totalAssets ?? 0
                  const total = walletSummary.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, (100 * lent) / total) : 0
                })()}%`,
              }}
            />
            <div
              className="h-full bg-amber-500/80 transition-all"
              style={{
                width: `${!walletSummary ? 0 : (() => {
                  const offers = walletSummary.total_offers_usd ?? 0
                  const total = walletSummary.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, (100 * offers) / total) : 0
                })()}%`,
              }}
            />
            <div
              className="h-full bg-muted-foreground/50 transition-all"
              style={{
                width: `${!walletSummary ? 0 : (() => {
                  const idle = walletSummary.idle_usd ?? 0
                  const total = walletSummary.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, (100 * idle) / total) : 0
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
              {t("liveStatus.inOrderBook")}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-muted-foreground/50" />
              {t("liveStatus.idleFunds")}
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
              {!walletSummary ? (loading ? "…" : "—") : `$${(walletSummary.total_lent_usd ?? totalAssets ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            <p className="text-xs text-emerald">
              {walletSummary?.total_usd_all && walletSummary.total_usd_all > 0
                ? `${(((walletSummary.total_lent_usd ?? totalAssets ?? 0) / walletSummary.total_usd_all) * 100).toFixed(1)}%`
                : walletSummary ? "0.0%" : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.returnGenerating")}</p>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.pendingDeployment")}</span>
              <Clock className="h-4 w-4 text-amber-500" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              {!walletSummary ? (loading ? "…" : "—") : `$${(walletSummary.total_offers_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            <p className="text-xs text-amber-500">
              {walletSummary?.total_usd_all && walletSummary.total_usd_all > 0
                ? `${(((walletSummary.total_offers_usd ?? 0) / walletSummary.total_usd_all) * 100).toFixed(1)}%`
                : walletSummary ? "0.0%" : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.inOrderBook")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/30 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.idleFunds")}</span>
              <Moon className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              {!walletSummary ? (loading ? "…" : "—") : `$${(walletSummary.idle_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            <p className="text-xs text-muted-foreground">
              {walletSummary?.total_usd_all && walletSummary.total_usd_all > 0
                ? `${(((walletSummary.idle_usd ?? 0) / walletSummary.total_usd_all) * 100).toFixed(1)}%`
                : walletSummary ? "0.0%" : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.cashDrag")}</p>
          </div>
        </div>
      </div>

      {/* Performance (key metrics) — only when we have full wallet data */}
      {walletSummary && (
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="h-5 w-5 text-amber-500" />
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.performance")}</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{t("liveStatus.keyMetrics")}</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-secondary/20 p-4">
            <p className="text-xs font-medium text-muted-foreground">{t("liveStatus.estDailyEarnings")}</p>
            <p className="mt-2 text-xl font-bold text-emerald">
              {!walletSummary ? "—" : `$${(walletSummary.est_daily_earnings_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            <p className="text-xs text-muted-foreground">{t("liveStatus.basedOnCurrentRates")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/20 p-4">
            <p className="text-xs font-medium text-muted-foreground">{t("liveStatus.weightedAvgApr")}</p>
            <p className="mt-2 text-xl font-bold text-blue-400">
              {!walletSummary ? "—" : `${(walletSummary.weighted_avg_apr_pct ?? 0).toFixed(2)}%`}
            </p>
            <p className="text-xs text-muted-foreground">{t("liveStatus.acrossAllActiveLending")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/20 p-4">
            <p className="text-xs font-medium text-muted-foreground">{t("liveStatus.yieldOverTotal")}</p>
            <p className="mt-2 text-xl font-bold text-foreground">
              {!walletSummary ? "—" : `${(walletSummary.yield_over_total_pct ?? 0).toFixed(2)}%`}
            </p>
            <p className="text-xs text-muted-foreground">{t("liveStatus.yieldOverTotalDesc")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/20 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.activeOrders")}</span>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              {!walletSummary ? "—" : String(walletSummary.credits_count ?? 0)}
            </p>
            <p className="text-xs text-muted-foreground">{t("liveStatus.activeLendingPositions")}</p>
          </div>
        </div>
      </div>
      )}

      {/* Personal Lending Ledger (active positions, 10 per page) — same wallet data, no extra API */}
      {walletSummary && (walletSummary.credits_detail?.length ?? 0) > 0 && (() => {
        const PER_PAGE = 10
        const list = walletSummary.credits_detail ?? []
        const totalPages = Math.max(1, Math.ceil(list.length / PER_PAGE))
        const page = Math.min(ledgerPage, totalPages)
        const start = (page - 1) * PER_PAGE
        const slice = list.slice(start, start + PER_PAGE)
        return (
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.personalLendingLedger")}</h3>
            <p className="text-xs text-muted-foreground mt-1">{t("liveStatus.personalLendingLedgerDesc")}</p>
            <div className="overflow-x-auto mt-4">
              <table className="w-full text-left text-xs" role="table">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="py-2 pr-2 font-medium">#</th>
                    <th className="py-2 font-medium">Symbol</th>
                    <th className="py-2 font-medium text-right">Amount</th>
                    <th className="py-2 font-medium text-right">Amount (USD)</th>
                    <th className="py-2 font-medium text-right">Rate (APR %)</th>
                    <th className="py-2 font-medium text-right">Period (d)</th>
                  </tr>
                </thead>
                <tbody>
                  {slice.map((row, i) => (
                    <tr key={row.id} className="border-b border-border/50">
                      <td className="py-2 pr-2 font-mono text-muted-foreground">{start + i + 1}</td>
                      <td className="py-2 font-medium text-foreground">{row.symbol}</td>
                      <td className="py-2 text-right font-mono text-foreground">{row.amount.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                      <td className="py-2 text-right font-mono text-foreground">${row.amount_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className="py-2 text-right font-mono text-emerald">{((row.rate * 365) * 100).toFixed(2)}%</td>
                      <td className="py-2 text-right font-mono text-muted-foreground">{row.period}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
                <span>
                  {start + 1}–{Math.min(start + PER_PAGE, list.length)} of {list.length}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setLedgerPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="rounded border border-border px-2 py-1 hover:bg-secondary/50 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    onClick={() => setLedgerPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="rounded border border-border px-2 py-1 hover:bg-secondary/50 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {/* 24h Lending Record: hide when user has no meaningful exposure (< $1 total) */}
      {walletSummary && (walletSummary.total_usd_all ?? 0) >= 1 && (
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
      )}
    </div>
  )
}
