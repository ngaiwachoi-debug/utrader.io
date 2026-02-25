"use client"

import { useEffect, useState } from "react"
import {
  Wallet,
  DollarSign,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  BarChart3,
} from "lucide-react"
import { useT } from "@/lib/i18n"
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
const USER_ID = 1

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

const lendingLedger = [
  { time: "02-25 16:00", range: "2.12 - 6.5%", maxDays: 4, cumulative: "$6,901,678.00", rate: "2.6363%", amount: "$794", count: 1, total: "$794" },
  { time: "02-25 15:00", range: "1.89 - 8.87%", maxDays: 7, cumulative: "$7,228,365.00", rate: "2.6364%", amount: "$212", count: 1, total: "$506" },
  { time: "02-25 14:00", range: "2.22 - 20.26%", maxDays: 120, cumulative: "$122,469,866.00", rate: "2.6382%", amount: "$1,500", count: 2, total: "$2,006" },
  { time: "02-25 13:00", range: "2.17 - 16.73%", maxDays: 120, cumulative: "$30,744,745.00", rate: "2.6386%", amount: "$7,065", count: 7, total: "$9,072" },
  { time: "02-25 12:00", range: "0.05 - 16.73%", maxDays: 30, cumulative: "$25,530,513.00", rate: "2.6390%", amount: "$1,936,323", count: 1, total: "$1,945,395" },
]

type WalletSummary = {
  total_usd_all: number
  usd_only: number
  per_currency: Record<string, number>
  per_currency_usd: Record<string, number>
}

export function LiveStatus() {
  const t = useT()
  const [activeTab, setActiveTab] = useState("total")
  const [totalAssets, setTotalAssets] = useState<number | null>(null)
  const [walletSummary, setWalletSummary] = useState<WalletSummary | null>(null)
  const [walletError, setWalletError] = useState<string | null>(null)
  const [botActive, setBotActive] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isStopping, setIsStopping] = useState(false)

  const refreshStatus = async () => {
    try {
      setLoading(true)
      setError(null)
      setWalletError(null)
      const [botRes, walletsRes] = await Promise.all([
        fetch(`${API_BASE}/bot-stats/${USER_ID}`),
        fetch(`${API_BASE}/wallets/${USER_ID}`),
      ])
      if (botRes.ok) {
        const data = await botRes.json()
        setBotActive(Boolean(data.active))
        const total = parseFloat(String(data.total_loaned ?? "0").replace(/,/g, ""))
        setTotalAssets(Number.isFinite(total) ? total : 0)
      } else {
        setBotActive(null)
        setTotalAssets(null)
      }
      if (walletsRes.ok) {
        const wallets = await walletsRes.json()
        setWalletSummary({
          total_usd_all: Number(wallets.total_usd_all) || 0,
          usd_only: Number(wallets.usd_only) || 0,
          per_currency: wallets.per_currency || {},
          per_currency_usd: wallets.per_currency_usd || {},
        })
      } else {
        setWalletSummary(null)
        setWalletError(t("liveStatus.connectApiKeys"))
      }
    } catch (e) {
      console.error("Failed to fetch live status", e)
      setError(t("liveStatus.unableToLoad"))
      setBotActive(null)
      setTotalAssets(null)
      setWalletSummary(null)
      setWalletError(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshStatus()
  }, [])

  const handleStart = async () => {
    try {
      setIsStarting(true)
      const res = await fetch(`${API_BASE}/start-bot/${USER_ID}`, { method: "POST" })
      if (!res.ok) {
        console.error("Start bot failed", await res.text())
      }
      await refreshStatus()
    } finally {
      setIsStarting(false)
    }
  }

  const handleStop = async () => {
    try {
      setIsStopping(true)
      const res = await fetch(`${API_BASE}/stop-bot/${USER_ID}`, { method: "POST" })
      if (!res.ok) {
        console.error("Stop bot failed", await res.text())
      }
      await refreshStatus()
    } finally {
      setIsStopping(false)
    }
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
            className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground hover:border-emerald/50 hover:text-foreground transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t("liveStatus.refresh")}
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
          </p>
        </div>

        {/* Currently loaned (from bot) */}
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
              {loading && totalAssets === null ? "…" : `$${(totalAssets ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {botActive ? "Bot is actively deploying lending capital." : "Bot is currently idle."}
          </p>
        </div>
      </div>

      {/* Charts & Market */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* 24h Lending Chart */}
        <div className="rounded-xl border border-border bg-card p-5 lg:col-span-3">
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

        {/* Market Overview */}
        <div className="rounded-xl border border-border bg-card lg:col-span-2">
          <div className="border-b border-border p-4">
            <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.marketOverview")}</h3>
          </div>
          {/* Market Header */}
          <div className="grid grid-cols-4 gap-2 border-b border-border px-4 py-2 text-xs font-medium text-muted-foreground">
            <span>Currency</span>
            <span className="text-right">{t("liveStatus.rate")}</span>
            <span className="text-right">1d Change</span>
            <span className="text-right">{t("liveStatus.volume")}</span>
          </div>
          {/* Market Rows */}
          <div className="max-h-[320px] overflow-y-auto">
            {marketData.map((item) => (
              <div
                key={item.currency}
                className="grid grid-cols-4 gap-2 border-b border-border/50 px-4 py-2.5 text-xs transition-colors hover:bg-secondary/30"
              >
                <div className="flex items-center gap-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-[10px] font-bold text-foreground">
                    {item.currency.charAt(0)}
                  </div>
                  <span className="font-medium text-foreground">{item.currency}</span>
                </div>
                <span className="text-right font-mono text-foreground">{item.rate}</span>
                <span
                  className={`text-right font-mono ${
                    item.dailyChange.startsWith("+") ? "text-emerald" : "text-destructive"
                  }`}
                >
                  {item.dailyChange}
                </span>
                <span className="text-right font-mono text-muted-foreground">{item.volume}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Lending Ledger Table */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border p-5">
          <h3 className="text-sm font-semibold text-foreground">{t("liveStatus.bitfinexLendingLedger")}</h3>
          <p className="text-xs text-muted-foreground">{t("liveStatus.lendingLedgerDesc")}</p>
        </div>

        {/* Current Rate Card */}
        <div className="m-5 rounded-xl bg-emerald/10 border border-emerald/20 p-5">
          <p className="text-xs text-muted-foreground">{t("liveStatus.currentAnnualRate")}</p>
          <p className="text-3xl font-bold text-emerald mt-1">$2.64%</p>
          <p className="text-xs text-muted-foreground mt-1">{t("liveStatus.dailyRate")} 0.007229</p>
        </div>

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
              {lendingLedger.map((row, i) => (
                <tr key={i} className="border-b border-border/50 transition-colors hover:bg-secondary/30">
                  <td className="px-5 py-3 font-mono text-foreground">{row.time}</td>
                  <td className="px-5 py-3 font-mono text-muted-foreground">{row.range}</td>
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
