"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter, usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import { clearBackendTokenCache, getBackendToken } from "@/lib/auth"
import { Star, Clock, Search, Bell, HelpCircle, User, Globe, Calendar, LogOut } from "lucide-react"
import { useLanguage } from "@/lib/i18n"
import { useSession } from "next-auth/react"
import { useDateRange } from "@/lib/date-range-context"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Calendar as CalendarComponent } from "@/components/ui/calendar"
import type { DateRange as PickerRange } from "react-day-picker"
import { useCurrentUserId } from "@/lib/current-user-context"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type CurrencyView = "USD" | "USDT"

type HeaderProps = { onUpgradeClick?: () => void }

export function Header({ onUpgradeClick }: HeaderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const { data: session, status } = useSession()
  const userId = useCurrentUserId()
  const { language, setLanguage, t } = useLanguage()
  const { range, setRange, formatRange } = useDateRange()
  const signedIn = status === "authenticated" && !!session?.user
  const [currencyView, setCurrencyView] = useState<CurrencyView>("USD")
  const [totalUsdAll, setTotalUsdAll] = useState<number | null>(null)
  const [usdOnly, setUsdOnly] = useState<number | null>(null)
  const [walletsLoading, setWalletsLoading] = useState(true)
  const [dateOpen, setDateOpen] = useState(false)
  const [tokensRemaining, setTokensRemaining] = useState<number | null>(null)
  const [lendingLimit, setLendingLimit] = useState<number>(250_000)
  const [walletDataSource, setWalletDataSource] = useState<"live" | "cache" | null>(null)
  const [walletRateLimited, setWalletRateLimited] = useState(false)

  useEffect(() => {
    if (userId == null) {
      setTotalUsdAll(null)
      setUsdOnly(null)
      setLendingLimit(250_000)
      setWalletDataSource(null)
      setWalletRateLimited(false)
      setWalletsLoading(false)
      return
    }
    let cancelled = false
    const run = async () => {
      setWalletsLoading(true)
      try {
        const token = await getBackendToken()
        const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
        const [walletRes, statusRes] = await Promise.all([
          fetch(`${API_BASE}/wallets/${userId}`, { credentials: "include", headers }),
          fetch(`${API_BASE}/user-status/${userId}`, { credentials: "include", headers }),
        ])
        if (cancelled) return
        if (walletRes.ok) {
          const data = await walletRes.json()
          setTotalUsdAll(Number(data.total_usd_all) ?? 0)
          setUsdOnly(Number(data.usd_only) ?? 0)
          const src = walletRes.headers.get("X-Data-Source")
          setWalletDataSource(src === "cache" ? "cache" : "live")
          setWalletRateLimited(walletRes.headers.get("X-Rate-Limited") === "true")
        } else {
          setTotalUsdAll(null)
          setUsdOnly(null)
          setWalletDataSource(null)
          setWalletRateLimited(false)
        }
        if (statusRes.ok) {
          const statusData = await statusRes.json()
          const tr = statusData.tokens_remaining
          setTokensRemaining(typeof tr === "number" ? tr : null)
          setLendingLimit(Number(statusData.lending_limit) ?? 250_000)
        }
      } catch {
        if (!cancelled) {
          setTotalUsdAll(null)
          setUsdOnly(null)
          setWalletDataSource(null)
          setWalletRateLimited(false)
          setTokensRemaining(null)
        }
      } finally {
        if (!cancelled) setWalletsLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [userId])

  const displayValue =
    currencyView === "USD"
      ? usdOnly != null
        ? `$${usdOnly.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
        : "—"
      : totalUsdAll != null
        ? `$${totalUsdAll.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
        : "—"

  const handleLocaleChange = (value: string) => {
    setLanguage(value as "en" | "zh")
    const locale = value === "zh" ? "zh" : "en"
    const path = pathname ?? "/dashboard"
    const hasLocale = /^\/(en|zh)(\/|$)/.test(path)
    if (hasLocale) {
      const withoutLocale = path.replace(/^\/(en|zh)/, "") || "/"
      const newPath = `/${locale}${withoutLocale === "/" ? "" : withoutLocale}`
      if (path !== newPath) router.push(newPath)
    }
  }

  const pickerRange: PickerRange | undefined = range
    ? { from: range.start, to: range.end }
    : undefined

  return (
    <header className="sticky top-0 z-30 flex flex-col border-b border-border bg-card/80 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between px-4 lg:px-6">
        <div className="flex items-center gap-2">
          <Link href="/dashboard" className="text-sm font-semibold text-foreground">
            uTrader<span className="text-[#10b981]">.io</span>
          </Link>
          <span className="text-sm text-muted-foreground">{t("header.dashboard")}</span>
        </div>

        <div className="flex items-center gap-2 lg:gap-3">
          {/* Date Range Picker */}
          <Popover open={dateOpen} onOpenChange={setDateOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="hidden md:flex items-center gap-2 rounded-lg border border-border bg-secondary px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary/80 transition-colors"
              >
                <Calendar className="h-3.5 w-3.5" />
                <span>{formatRange()}</span>
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0 bg-card border-border" align="end">
              <CalendarComponent
                mode="range"
                selected={pickerRange}
                onSelect={(v) => {
                  if (v?.from) {
                    setRange({
                      start: v.from,
                      end: v.to ?? v.from,
                    })
                    setDateOpen(false)
                  }
                }}
                numberOfMonths={2}
                defaultMonth={range.start}
              />
            </PopoverContent>
          </Popover>

          {/* Currency Select: USD | USDT (do not translate) */}
          <Select
            value={currencyView}
            onValueChange={(v) => setCurrencyView(v as CurrencyView)}
          >
            <SelectTrigger size="sm" className="hidden sm:flex w-[120px] text-xs border-border bg-secondary">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="USD">USD</SelectItem>
              <SelectItem value="USDT">USDT</SelectItem>
            </SelectContent>
          </Select>
          <span className="hidden sm:inline text-foreground font-medium min-w-[4rem] text-right text-xs" title={walletRateLimited ? t("header.rateLimited") : walletDataSource === "cache" ? t("header.dataCached") : undefined}>
            {walletsLoading ? "…" : displayValue}
            {!walletsLoading && walletDataSource === "cache" && (
              <span className="ml-1 text-[10px] text-muted-foreground">({t("header.dataCached")})</span>
            )}
            {walletRateLimited && (
              <span className="ml-1 text-[10px] text-amber-600 dark:text-amber-400" title={t("header.rateLimited")}>⚠</span>
            )}
          </span>

          <div className="flex items-center gap-1">
            <button className="rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors" aria-label={t("header.search")}>
              <Search className="h-4 w-4" />
            </button>
            <button className="relative rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors" aria-label={t("header.notifications")}>
              <Bell className="h-4 w-4" />
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[#10b981]" />
            </button>
            <button className="hidden sm:flex rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors" aria-label={t("header.help")}>
              <HelpCircle className="h-4 w-4" />
            </button>
            {signedIn ? (
              <button
                onClick={() => { clearBackendTokenCache(); signOut({ callbackUrl: "/" }).then(() => router.refresh()) }}
                className="hidden sm:flex items-center gap-1.5 rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                aria-label={t("header.logout")}
              >
                <LogOut className="h-4 w-4" />
                <span className="text-xs">{t("header.logout")}</span>
              </button>
            ) : (
              <Link href="/login" className="hidden sm:flex items-center gap-1.5 rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                <User className="h-4 w-4" />
                <span className="text-xs">{t("header.login")}</span>
              </Link>
            )}
            {/* Language Select: English | 中文, toggle /en and /zh */}
            <Select value={language} onValueChange={handleLocaleChange}>
              <SelectTrigger size="sm" className="hidden sm:flex w-[100px] text-xs border-border bg-secondary">
                <Globe className="h-3.5 w-3.5 mr-1" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="zh">中文</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Token / Plan Banner */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border bg-card px-4 py-2 lg:px-6">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <Star className="h-3.5 w-3.5 text-yellow-400" />
            <span className="rounded-full bg-[#10b981] px-2.5 py-0.5 text-xs font-semibold text-primary-foreground">
              {tokensRemaining !== null ? `${Math.round(tokensRemaining)} tokens` : "—"}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            <span>{t("header.lendingLimit")}: ${(lendingLimit ?? 0).toLocaleString()}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden lg:inline text-xs text-muted-foreground">
            {t("header.keepEarning")}
          </span>
          <button
            onClick={() => onUpgradeClick?.()}
            className="rounded-lg bg-emerald px-4 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-emerald/90 transition-colors"
          >
            {t("header.upgradeNow")}
          </button>
        </div>
      </div>
    </header>
  )
}
