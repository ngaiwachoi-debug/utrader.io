"use client"

import { useEffect, useState } from "react"
import { useT } from "@/lib/i18n"
import { BarChart3, TrendingUp, DollarSign, PieChart, Activity, BookOpen } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type FundingSymbolOption = { value: string; label: string }

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
  const [ledgerSymbols, setLedgerSymbols] = useState<FundingSymbolOption[]>([])
  const [ledgerSymbol, setLedgerSymbol] = useState<string>("fUSD")
  const [ledgerCurrentRate, setLedgerCurrentRate] = useState<string | null>(null)
  const [ledgerDailyRate, setLedgerDailyRate] = useState<number | null>(null)
  const [ledgerRows, setLedgerRows] = useState<LendingLedgerRow[]>([])
  const [ledgerLoading, setLedgerLoading] = useState(false)
  const [ledgerError, setLedgerError] = useState<string | null>(null)

  const fetchLedger = async (symbol: string) => {
    try {
      setLedgerLoading(true)
      setLedgerError(null)
      const res = await fetch(`${API_BASE}/api/funding-ledger?symbol=${encodeURIComponent(symbol)}`)
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
    } catch {
      setLedgerError("Failed to load ledger")
      setLedgerRows([])
      setLedgerCurrentRate(null)
      setLedgerDailyRate(null)
    } finally {
      setLedgerLoading(false)
    }
  }

  useEffect(() => {
    fetch(`${API_BASE}/api/funding-symbols`)
      .then((res) => res.json())
      .then((data: FundingSymbolOption[]) => {
        if (Array.isArray(data) && data.length > 0) setLedgerSymbols(data)
        else setLedgerSymbols([{ value: "fUSD", label: "USD" }, { value: "fUST", label: "USDt" }, { value: "fBTC", label: "BTC" }, { value: "fETH", label: "ETH" }, { value: "fXRP", label: "XRP" }])
      })
      .catch(() => setLedgerSymbols([{ value: "fUSD", label: "USD" }, { value: "fUST", label: "USDt" }, { value: "fBTC", label: "BTC" }, { value: "fETH", label: "ETH" }, { value: "fXRP", label: "XRP" }]))
  }, [])

  useEffect(() => {
    fetchLedger(ledgerSymbol)
  }, [ledgerSymbol])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-primary">Bitfinex Lending</p>
        <h1 className="text-2xl font-bold text-foreground">{t("marketStatus.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("marketStatus.subtitle")}</p>
      </div>

      {/* Market cards row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Total Market Volume (24h)</span>
            <DollarSign className="h-4 w-4 text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground">$775.3M</p>
          <p className="text-xs text-muted-foreground">USD + USDt combined</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Avg. USD Lend Rate</span>
            <TrendingUp className="h-4 w-4 text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold text-primary">2.63%</p>
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
            <PieChart className="h-4 w-4 text-primary" />
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
                  item.dailyChange.startsWith("+") ? "text-primary" : "text-destructive"
                }`}
              >
                {item.dailyChange}
              </span>
              <span className="text-right font-mono text-muted-foreground">{item.volume}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Lending Ledger (market data): symbol selector + rate + 24h history */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border p-4">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{t("marketStatus.lendingLedger")}</h3>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{t("liveStatus.lendingLedgerDesc")}</p>
          <div className="mt-3">
            <label htmlFor="ledger-currency" className="sr-only">{t("marketStatus.selectCurrency")}</label>
            <select
              id="ledger-currency"
              value={ledgerSymbol}
              onChange={(e) => setLedgerSymbol(e.target.value)}
              className="rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              {ledgerSymbols.length === 0 && <option value="fUSD">USD</option>}
              {ledgerSymbols.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="m-5 rounded-xl bg-primary/10 border border-primary/20 p-5">
          <p className="text-xs text-muted-foreground">{t("liveStatus.currentAnnualRate")}</p>
          <p className="text-3xl font-bold text-primary mt-1">
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
                  <td className="px-5 py-3 text-right font-bold font-mono text-primary">{row.rate}</td>
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
