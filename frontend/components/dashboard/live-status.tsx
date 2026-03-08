"use client"

import { useEffect, useRef, useState } from "react"
import {
  Wallet,
  DollarSign,
  TrendingUp,
  BarChart3,
  PieChart,
  Activity,
  Clock,
  Moon,
} from "lucide-react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useBotStatus } from "@/lib/bot-status-context"
import { useWallets, useBotStats } from "@/lib/dashboard-data-context"
import { BotStatusBar } from "@/components/dashboard/bot-status-bar"
import { Spinner } from "@/components/ui/spinner"
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

const REFRESH_COOLDOWN_SEC = 15

export function LiveStatus() {
  const t = useT()
  const userId = useCurrentUserId()
  const id = userId ?? 0
  const wallets = useWallets(id)
  const botStats = useBotStats(id)
  const botCtx = useBotStatus()
  const botActive = botStats.data?.active ?? botCtx?.botActive ?? null
  const [refreshCooldownUntil, setRefreshCooldownUntil] = useState(0)
  const [refreshCooldownSec, setRefreshCooldownSec] = useState(0)
  const [ledgerPage, setLedgerPage] = useState(1)
  const lastCooldownSecRef = useRef(0)

  useEffect(() => {
    const interval = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((refreshCooldownUntil - Date.now()) / 1000))
      if (remaining !== lastCooldownSecRef.current) {
        lastCooldownSecRef.current = remaining
        setRefreshCooldownSec(remaining)
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [refreshCooldownUntil])

  useEffect(() => {
    const len = wallets.data?.credits_detail?.length ?? 0
    if (len > 0) setLedgerPage(1)
  }, [wallets.data?.credits_detail?.length])

  // When Live Status tab is shown, ensure we have data: refetch once after a short delay so we don't rely only on
  // initial prefetch (which may still be in progress or may have failed).
  useEffect(() => {
    if (userId == null) return
    const t = setTimeout(() => {
      if (!wallets.data) void wallets.refetch()
      if (!botStats.data) void botStats.refetch()
    }, 600)
    return () => clearTimeout(t)
  }, [userId])

  const handleRefresh = () => {
    if (userId == null) return
    if (Date.now() < refreshCooldownUntil) return
    setRefreshCooldownUntil(Date.now() + REFRESH_COOLDOWN_SEC * 1000)
    void wallets.refetch()
    void botStats.refetch()
  }

  const walletSummary = wallets.data
  const walletError = wallets.error
  const loading = wallets.loading && !wallets.data
  const walletDataSource = wallets.source
  const walletRateLimited = wallets.rateLimited
  const totalAssets = botStats.data?.total_loaned ?? null
  const error = wallets.error || botStats.error || null

  const displayTotalUsd = walletSummary?.total_usd_all ?? totalAssets ?? 0
  const displayTotalLent = walletSummary?.total_lent_usd ?? totalAssets ?? 0
  const displayWalletSummary = walletSummary

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
      <BotStatusBar
        title={t("liveStatus.title")}
        date="February 25, 2026"
        onRefresh={handleRefresh}
        refreshCooldownSec={refreshCooldownSec}
      />

      {(wallets.isRevalidating || botStats.isRevalidating) && (
        <p className="text-xs text-muted-foreground">Updating…</p>
      )}

      {(error || botCtx?.error) && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error || botCtx?.error}
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Client assets (Bitfinex total) */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">{t("liveStatus.assets")}</span>
              <span className="text-xs text-muted-foreground">{t("liveStatus.allCurrencies")}</span>
            </div>
            <Wallet className="h-5 w-5 text-primary" />
          </div>
          <div className="mt-3">
            {loading && !displayWalletSummary ? (
              <span className="flex items-center gap-2 text-3xl font-bold text-foreground">
                <Spinner className="h-8 w-8" />
                <span className="text-muted-foreground">Loading…</span>
              </span>
            ) : (
              <span className="text-3xl font-bold text-foreground">
                {!displayWalletSummary ? "—" : `$${(displayTotalUsd ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {walletError ?? (displayWalletSummary ? t("liveStatus.totalUsdValue") : loading ? t("liveStatus.loading") : "—")}
            {walletError === "Data incomplete" && (
              <span className="block mt-1 text-primary">
                Wallet totals ($) come from Bitfinex; snapshot failed (Redis/nonce or rate limit). Token amount and other pages use the app DB and load separately. Use <strong>Refresh</strong> above to retry.
              </span>
            )}
            {!loading && !walletError && (displayTotalUsd ?? 0) === 0 && (
              <span className="block mt-1 text-primary">
                No data: Connect Bitfinex API keys with wallets/read permission, or the API may be rate limited. Total USD is from Bitfinex funding wallets only.
              </span>
            )}
            {walletDataSource === "cache" && !walletError && (
              <span className="ml-1 text-muted-foreground"> · {t("liveStatus.dataCached")}</span>
            )}
            {walletRateLimited && (
              <span className="ml-1 text-primary" title={t("liveStatus.rateLimited")}> · ⚠ {t("liveStatus.rateLimited")}</span>
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
            <DollarSign className="h-5 w-5 text-primary" />
          </div>
          <div className="mt-3">
            {loading && !displayWalletSummary ? (
              <span className="flex items-center gap-2 text-3xl font-bold text-foreground">
                <Spinner className="h-8 w-8" />
                <span className="text-muted-foreground">Loading…</span>
              </span>
            ) : (
              <span className="text-3xl font-bold text-foreground">
                {!displayWalletSummary ? "—" : `$${(displayTotalLent ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {botActive ? "Bot is actively deploying lending capital." : "Bot is currently idle."}
            {!loading && (displayTotalLent ?? 0) === 0 && (
              <span className="block mt-1 text-primary">
                No data: Same as Assets — Bitfinex keys and wallets/read required.
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Portfolio Allocation */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <PieChart className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.portfolioAllocation")}</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{t("liveStatus.capitalDeploymentOverview")}</p>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          {loading && !displayWalletSummary ? (
            <span className="flex items-center gap-2 text-xl font-bold text-primary">
              <Spinner className="h-5 w-5" />
              <span className="text-muted-foreground">Loading…</span>
            </span>
          ) : (
            <span className="text-xl font-bold text-primary">
              {!displayWalletSummary ? "—" : `$${(displayTotalUsd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </span>
          )}
          <span className="text-xs text-muted-foreground">{displayWalletSummary ? "100.0% Active" : "—"}</span>
          <span className="text-xs text-muted-foreground">{displayWalletSummary ? "100.0% deployed" : "—"}</span>
        </div>
        <div className="mb-4">
          <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
            <span>{t("liveStatus.allocationBreakdown")}</span>
          </div>
          <div className="h-3 w-full rounded-full bg-secondary overflow-hidden flex">
            <div
              className="h-full bg-primary transition-all"
              style={{
                width: `${!displayWalletSummary ? 0 : (() => {
                  const lent = displayWalletSummary.total_lent_usd ?? totalAssets ?? 0
                  const total = displayWalletSummary.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, (100 * lent) / total) : 0
                })()}%`,
              }}
            />
            <div
              className="h-full bg-gold-dim transition-all"
              style={{
                width: `${!displayWalletSummary ? 0 : (() => {
                  const offers = displayWalletSummary.total_offers_usd ?? 0
                  const total = displayWalletSummary.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, (100 * offers) / total) : 0
                })()}%`,
              }}
            />
            <div
              className="h-full bg-muted-foreground/50 transition-all"
              style={{
                width: `${!displayWalletSummary ? 0 : (() => {
                  const idle = displayWalletSummary.idle_usd ?? 0
                  const total = displayWalletSummary.total_usd_all ?? 0
                  return total > 0 ? Math.min(100, (100 * idle) / total) : 0
                })()}%`,
              }}
            />
          </div>
          <div className="flex gap-4 mt-1.5 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-primary" />
              {t("liveStatus.earning")}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-gold-dim" />
              {t("liveStatus.inOrderBook")}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-muted-foreground/50" />
              {t("liveStatus.idleFunds")}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.activelyEarning")}</span>
              <Activity className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              {!displayWalletSummary ? (loading ? "…" : "—") : `$${(displayWalletSummary.total_lent_usd ?? totalAssets ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            <p className="text-xs text-primary">
              {displayWalletSummary?.total_usd_all && displayWalletSummary.total_usd_all > 0
                ? `${(((displayWalletSummary.total_lent_usd ?? totalAssets ?? 0) / displayWalletSummary.total_usd_all) * 100).toFixed(1)}%`
                : displayWalletSummary ? "0.0%" : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.returnGenerating")}</p>
          </div>
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.pendingDeployment")}</span>
              <Clock className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              {!displayWalletSummary ? (loading ? "…" : "—") : `$${(displayWalletSummary.total_offers_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            <p className="text-xs text-primary">
              {displayWalletSummary?.total_usd_all && displayWalletSummary.total_usd_all > 0
                ? `${(((displayWalletSummary.total_offers_usd ?? 0) / displayWalletSummary.total_usd_all) * 100).toFixed(1)}%`
                : displayWalletSummary ? "0.0%" : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.inOrderBook")}</p>
          </div>
          <div className="rounded-xl border border-border bg-secondary/30 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.idleFunds")}</span>
              <Moon className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-xl font-bold text-foreground">
              {!displayWalletSummary ? (loading ? "…" : "—") : `$${(displayWalletSummary.idle_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            <p className="text-xs text-muted-foreground">
              {displayWalletSummary?.total_usd_all && displayWalletSummary.total_usd_all > 0
                ? `${(((displayWalletSummary.idle_usd ?? 0) / displayWalletSummary.total_usd_all) * 100).toFixed(1)}%`
                : displayWalletSummary ? "0.0%" : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("liveStatus.cashDrag")}</p>
          </div>
        </div>
      </div>

      {/* Currently Lent Out: bar per currency (Amount lent | Pending | Idle); hide if total USD < 1 */}
      {displayWalletSummary && (() => {
        const lentUsd = displayWalletSummary.lent_per_currency_usd ?? {}
        const offersUsd = displayWalletSummary.offers_per_currency_usd ?? {}
        const idleUsd = displayWalletSummary.idle_per_currency_usd ?? {}
        const MIN_DISPLAY_USD = 1
        const currencies = Array.from(new Set([
          ...Object.keys(displayWalletSummary.per_currency_usd ?? {}),
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
                        className="h-full bg-primary transition-all"
                        style={{ width: `${Math.min(100, pct(lent))}%` }}
                        title={`Amount lent: $${lent.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                      />
                      <div
                        className="h-full bg-gold-dim transition-all"
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
                        <span className="h-1.5 w-3 rounded-full bg-primary" />
                        {t("liveStatus.earning")}: ${lent.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-1.5 w-3 rounded-full bg-amber-600 dark:bg-amber-500/80" />
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

      {/* Performance (key metrics) — True ROI–style cards */}
      {displayWalletSummary && (
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.performance")}</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{t("liveStatus.keyMetrics")}</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.estDailyEarnings")}</span>
              <DollarSign className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-3">
              <span className="text-3xl font-bold text-primary">
                {!displayWalletSummary ? "—" : `$${(displayWalletSummary.est_daily_earnings_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("liveStatus.basedOnCurrentRates")}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.weightedAvgApr")}</span>
              <TrendingUp className="h-4 w-4 text-blue-400" />
            </div>
            <div className="mt-3">
              <span className="text-3xl font-bold text-foreground">
                {!displayWalletSummary ? "—" : `${(displayWalletSummary.weighted_avg_apr_pct ?? 0).toFixed(2)}%`}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("liveStatus.acrossAllActiveLending")}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.takenOrders")}</span>
              <Activity className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-3">
              <span className="text-3xl font-bold text-foreground">
                {!displayWalletSummary ? "—" : String(displayWalletSummary.credits_count ?? 0)}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("liveStatus.takenOrdersDesc")}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t("liveStatus.ordersNotTaken")}</span>
              <BarChart3 className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-3">
              <span className="text-3xl font-bold text-foreground">
                {!displayWalletSummary ? "—" : String(displayWalletSummary.offers_count ?? 0)}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("liveStatus.ordersNotTakenDesc")}</p>
          </div>
        </div>
      </div>
      )}

      {/* Personal Lending Ledger (active positions, 10 per page) — same wallet data, no extra API */}
      {displayWalletSummary && (displayWalletSummary.credits_detail?.length ?? 0) > 0 && (() => {
        const PER_PAGE = 10
        const list = displayWalletSummary.credits_detail ?? []
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
                      <td className="py-2 text-right font-mono text-primary">{((row.rate * 365) * 100).toFixed(2)}%</td>
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
      {displayWalletSummary && (displayWalletSummary.total_usd_all ?? 0) >= 1 && (
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-foreground">24h Lending Record</h3>
          <p className="text-xs text-muted-foreground">{t("liveStatus.realtimeLending")}</p>
        </div>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2b3139" />
              <XAxis dataKey="time" tick={{ fill: "#848e9c", fontSize: 10 }} axisLine={{ stroke: "#2b3139" }} />
              <YAxis yAxisId="left" tick={{ fill: "#848e9c", fontSize: 10 }} axisLine={{ stroke: "#2b3139" }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#848e9c", fontSize: 10 }} axisLine={{ stroke: "#2b3139" }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1e2329",
                  borderColor: "#2b3139",
                  borderRadius: "8px",
                  color: "#eaecef",
                  fontSize: "12px",
                }}
              />
              <Line yAxisId="left" type="monotone" dataKey="usdVolume" stroke="#0ecb81" strokeWidth={2} dot={false} name="USD Volume" />
              <Line yAxisId="left" type="monotone" dataKey="usdtVolume" stroke="#ea4b4b" strokeWidth={2} dot={false} name="USDt Volume" />
              <Bar yAxisId="right" dataKey="usdRate" fill="#0ecb81" opacity={0.3} name="USD Rate %" />
              <Bar yAxisId="right" dataKey="usdtRate" fill="#ea4b4b" opacity={0.3} name="USDt Rate %" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-6 rounded-full bg-primary"></span>
            USD Volume
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-6 rounded-full bg-destructive"></span>
            USDt Volume
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-6 rounded-full bg-primary/30"></span>
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
