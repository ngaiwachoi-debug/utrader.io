"use client"

import { useEffect, useState } from "react"
import {
  DollarSign,
  TrendingUp,
  Percent,
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  BarChart3,
  Clock,
  Info,
} from "lucide-react"
import { useDateRange } from "@/lib/date-range-context"
import { useT } from "@/lib/i18n"
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
const USER_ID = 1

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

export function ProfitCenter() {
  const t = useT()
  const { range } = useDateRange()
  const [timeRange, setTimeRange] = useState("30d")
  const [grossProfit, setGrossProfit] = useState<number | null>(null)
  const [platformFee, setPlatformFee] = useState<number | null>(null)
  const [netProfit, setNetProfit] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true)
        setError(null)
        const start = range.start.toISOString().slice(0, 10)
        const end = range.end.toISOString().slice(0, 10)
        const res = await fetch(`${API_BASE}/stats/${USER_ID}?start=${start}&end=${end}`)
        if (!res.ok) {
          throw new Error("Failed to load profit stats")
        }
        const data = await res.json()
        setGrossProfit(data.gross_profit ?? 0)
        setPlatformFee(data.fake_fee ?? 0)
        setNetProfit(data.net_profit ?? 0)
      } catch (e) {
        console.error("Failed to fetch stats", e)
        setError(t("dashboard.unableToLoadProfit"))
      } finally {
        setLoading(false)
      }
    }

    fetchStats()
  }, [range.start, range.end])

  return (
    <div className="flex flex-col gap-6">
      {/* Page Title */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("dashboard.profitCenter")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("dashboard.profitCenterDesc")}
        </p>
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
            <span className="text-2xl font-bold text-foreground">
              {loading && grossProfit === null ? "…" : `$${(grossProfit ?? 0).toFixed(2)}`}
            </span>
            <span className="flex items-center gap-0.5 text-xs font-medium text-emerald">
              <ArrowUpRight className="h-3 w-3" />
              +12.4%
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.totalInterestThisPeriod")}</p>
        </div>

        {/* Platform Fee */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {t("dashboard.platformFee")}
            </span>
            <Percent className="h-4 w-4 text-chart-2" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-foreground">
              {loading && platformFee === null ? "…" : `-$${(platformFee ?? 0).toFixed(2)}`}
            </span>
            <div className="flex items-center gap-1">
              <Info className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">{t("dashboard.displayOnly")}</span>
            </div>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.visualFeeBreakdown")}</p>
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
            <span className="flex items-center gap-0.5 text-xs font-medium text-emerald">
              <ArrowUpRight className="h-3 w-3" />
              +12.4%
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.takeHomeIncome")}</p>
        </div>
      </div>

      {/* Trial Countdown Bar */}
      <div className="rounded-xl border border-emerald/20 bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald/10">
              <Clock className="h-5 w-5 text-emerald" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">{t("dashboard.proTrialCard")}</p>
              <p className="text-xs text-muted-foreground">{t("dashboard.expertPlanFeatures")}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold text-emerald">9 {t("dashboard.daysRemainingShort")}</span>
            <button className="rounded-lg bg-emerald px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-emerald-dark transition-colors">
              {t("dashboard.upgradeToPro")}
            </button>
          </div>
        </div>
        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span>{t("dashboard.trialProgress")}</span>
            <span>{t("dashboard.dayXofY", { n: 5, total: 7 })}</span>
          </div>
          <div className="h-2 w-full rounded-full bg-secondary">
            <div
              className="h-2 rounded-full bg-gradient-to-r from-emerald to-emerald-light transition-all duration-500"
              style={{ width: "71%" }}
            />
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
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
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
          </div>
        </div>

        {/* Interest Earned Chart */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-foreground">{t("dashboard.interestEarned")}</h3>
            <p className="text-xs text-muted-foreground">{t("dashboard.interestEarnedDesc")}</p>
          </div>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
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
