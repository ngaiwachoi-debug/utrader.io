"use client"

import {
  TrendingUp,
  DollarSign,
  Activity,
  ArrowUpRight,
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
} from "recharts"

const MONTH_ABBR: Record<string, number> = {
  Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5,
  Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11,
}

function parseChartDate(dateStr: string, year: number): Date {
  const [month, day] = dateStr.split(" ")
  const m = MONTH_ABBR[month] ?? 0
  return new Date(year, m, parseInt(day, 10))
}

const navHistory = [
  { date: "Jan 26", nav: 1.0, capital: 0 },
  { date: "Jan 30", nav: 1.0001, capital: 0 },
  { date: "Feb 03", nav: 1.0002, capital: 0 },
  { date: "Feb 07", nav: 1.0001, capital: 0 },
  { date: "Feb 11", nav: 1.0003, capital: 0 },
  { date: "Feb 15", nav: 1.0002, capital: 0 },
  { date: "Feb 19", nav: 1.0004, capital: 0 },
  { date: "Feb 25", nav: 1.0005, capital: 0 },
]

export function TrueROI() {
  const t = useT()
  const { range } = useDateRange()
  const year = range.start.getFullYear()
  const filteredNavHistory = navHistory.filter((d) => {
    const date = parseChartDate(d.date, year)
    return date >= range.start && date <= range.end
  })
  const chartData = filteredNavHistory.length ? filteredNavHistory : navHistory

  return (
    <div className="flex flex-col gap-6">
      {/* Page Title */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("dashboard.trueRoiTitle")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("dashboard.trueRoiDesc")}
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {/* NAV */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">{t("dashboard.nav")}</span>
            <Activity className="h-4 w-4 text-[#10b981]" />
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold text-foreground">1.0000</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.navPerUnit")}</p>
        </div>

        {/* True ROI */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">{t("dashboard.trueRoi")}</span>
            <TrendingUp className="h-4 w-4 text-[#10b981]" />
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold text-[#10b981]">+0.00%</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.pureYieldInception")}</p>
        </div>

        {/* Net Capital Flow */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">{t("dashboard.capitalFlow")}</span>
            <DollarSign className="h-4 w-4 text-[#10b981]" />
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold text-[#10b981]">+$0.00</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("dashboard.depositsWithdrawals")}</p>
        </div>
      </div>

      {/* NAV vs Capital Flow History */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-foreground">{t("dashboard.navVsCapitalTitle")}</h3>
          <p className="text-xs text-muted-foreground">{t("dashboard.navVsCapitalDesc")}</p>
        </div>
        <div className="h-[350px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="navGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={{ stroke: "#1e293b" }} />
              <YAxis domain={[0.9995, 1.001]} tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={{ stroke: "#1e293b" }} />
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
                dataKey="nav"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#navGradient)"
                name="NAV"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Capital Ledger */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border p-5">
          <h3 className="text-sm font-semibold text-foreground">{t("dashboard.capitalLedger")}</h3>
          <p className="text-xs text-muted-foreground">{t("dashboard.capitalLedgerDesc")}</p>
        </div>
        <div className="flex flex-col items-center justify-center py-16">
          <Activity className="h-10 w-10 text-muted-foreground/30 mb-3" />
          <p className="text-sm text-muted-foreground">{t("dashboard.noCapitalTransactions")}</p>
        </div>
      </div>
    </div>
  )
}
