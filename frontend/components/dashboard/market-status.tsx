"use client"

import { useT } from "@/lib/i18n"
import { BarChart3, TrendingUp, DollarSign, PieChart, Activity } from "lucide-react"

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

export function MarketStatus() {
  const t = useT()

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-emerald">Bitfinex Lending</p>
        <h1 className="text-2xl font-bold text-foreground">{t("marketStatus.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("marketStatus.subtitle")}</p>
      </div>

      {/* Market cards row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Total Market Volume (24h)</span>
            <DollarSign className="h-4 w-4 text-emerald" />
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground">$775.3M</p>
          <p className="text-xs text-muted-foreground">USD + USDt combined</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Avg. USD Lend Rate</span>
            <TrendingUp className="h-4 w-4 text-emerald" />
          </div>
          <p className="mt-2 text-2xl font-bold text-emerald">2.63%</p>
          <p className="text-xs text-muted-foreground">Current FRR</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Avg. USDt Lend Rate</span>
            <BarChart3 className="h-4 w-4 text-blue-400" />
          </div>
          <p className="mt-2 text-2xl font-bold text-blue-400">6.49%</p>
          <p className="text-xs text-muted-foreground">Current FRR</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Active Currencies</span>
            <Activity className="h-4 w-4 text-amber-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground">10+</p>
          <p className="text-xs text-muted-foreground">With lending depth</p>
        </div>
      </div>

      {/* Market Overview table */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border p-4">
          <div className="flex items-center gap-2">
            <PieChart className="h-4 w-4 text-emerald" />
            <h3 className="text-sm font-semibold text-foreground">Market Overview</h3>
          </div>
          <p className="text-xs text-muted-foreground mt-1">Rates and volume by currency</p>
        </div>
        <div className="grid grid-cols-4 gap-2 border-b border-border px-4 py-2 text-xs font-medium text-muted-foreground">
          <span>Currency</span>
          <span className="text-right">Rate</span>
          <span className="text-right">1d Change</span>
          <span className="text-right">Volume</span>
        </div>
        <div className="max-h-[400px] overflow-y-auto">
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
  )
}
