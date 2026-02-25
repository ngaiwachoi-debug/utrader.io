"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { signOut } from "next-auth/react"
import { Star, Clock, Search, Bell, HelpCircle, User, Globe, Calendar, LogOut } from "lucide-react"
import { useLanguage } from "@/lib/i18n"
import { useSession } from "next-auth/react"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"
const USER_ID = 1

type CurrencyView = "all" | "usd"

export function Header() {
  const router = useRouter()
  const { data: session, status } = useSession()
  const { language, setLanguage, t } = useLanguage()
  const signedIn = status === "authenticated" && !!session?.user
  const [currencyView, setCurrencyView] = useState<CurrencyView>("all")
  const [totalUsdAll, setTotalUsdAll] = useState<number | null>(null)
  const [usdOnly, setUsdOnly] = useState<number | null>(null)
  const [walletsLoading, setWalletsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setWalletsLoading(true)
      try {
        const res = await fetch(`${API_BASE}/wallets/${USER_ID}`)
        if (cancelled) return
        if (res.ok) {
          const data = await res.json()
          setTotalUsdAll(Number(data.total_usd_all) ?? 0)
          setUsdOnly(Number(data.usd_only) ?? 0)
        } else {
          setTotalUsdAll(null)
          setUsdOnly(null)
        }
      } catch {
        if (!cancelled) {
          setTotalUsdAll(null)
          setUsdOnly(null)
        }
      } finally {
        if (!cancelled) setWalletsLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [])

  const displayValue = currencyView === "usd"
    ? (usdOnly != null ? `$${usdOnly.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—")
    : (totalUsdAll != null ? `$${totalUsdAll.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—")

  return (
    <header
      className="sticky top-0 z-30 flex flex-col border-b border-border bg-card/80 backdrop-blur-md"
    >
      {/* Main header */}
      <div className="flex h-14 items-center justify-between px-4 lg:px-6">
        <div className="flex items-center gap-2">
          <Link href="/dashboard" className="text-sm font-semibold text-foreground">
            uTrader<span className="text-emerald">.io</span>
          </Link>
          <span className="text-sm text-muted-foreground">{t("header.dashboard")}</span>
        </div>

        <div className="flex items-center gap-2 lg:gap-3">
          {/* Date Range */}
          <div className="hidden md:flex items-center gap-2 rounded-lg border border-border bg-secondary px-3 py-1.5 text-xs text-muted-foreground">
            <Calendar className="h-3.5 w-3.5" />
            <span>Jan 26, 2026 - Feb 25, 2026</span>
          </div>

          {/* Currency Selector: All currencies (total USD) / USD only */}
          <div className="hidden sm:flex items-center gap-2 rounded-lg border border-border bg-secondary px-3 py-1.5 text-xs text-muted-foreground">
            <button
              type="button"
              onClick={() => setCurrencyView("all")}
              className={`cursor-pointer hover:text-foreground transition-colors ${currencyView === "all" ? "font-semibold text-foreground" : ""}`}
            >
              {t("header.allCurrencies")}
            </button>
            <span className="text-muted-foreground/60">|</span>
            <button
              type="button"
              onClick={() => setCurrencyView("usd")}
              className={`cursor-pointer hover:text-foreground transition-colors ${currencyView === "usd" ? "font-semibold text-foreground" : ""}`}
            >
              {t("header.usd")}
            </button>
            <span className="text-foreground font-medium min-w-[4rem] text-right">
              {walletsLoading ? "…" : displayValue}
            </span>
          </div>

          {/* Icon Buttons */}
          <div className="flex items-center gap-1">
            <button className="rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors" aria-label={t("header.search")}>
              <Search className="h-4 w-4" />
            </button>
            <button className="relative rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors" aria-label={t("header.notifications")}>
              <Bell className="h-4 w-4" />
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-emerald"></span>
            </button>
            <button className="hidden sm:flex rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors" aria-label={t("header.help")}>
              <HelpCircle className="h-4 w-4" />
            </button>
            {signedIn ? (
              <button
                onClick={() => signOut({ callbackUrl: "/" }).then(() => router.refresh())}
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
            <div className="hidden sm:flex items-center gap-1 rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
              <Globe className="h-4 w-4" />
              <button
                className={`text-xs ${language === "en" ? "font-semibold text-foreground" : ""}`}
                onClick={() => setLanguage("en")}
              >
                {t("header.langEn")}
              </button>
              <span className="text-xs text-muted-foreground">/</span>
              <button
                className={`text-xs ${language === "zh" ? "font-semibold text-foreground" : ""}`}
                onClick={() => setLanguage("zh")}
              >
                {t("header.langZh")}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Trial Banner */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border bg-card px-4 py-2 lg:px-6">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <Star className="h-3.5 w-3.5 text-yellow-400" />
            <span className="rounded-full bg-emerald px-2.5 py-0.5 text-xs font-semibold text-primary-foreground">
              {t("header.proTrial")}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            <span className="font-medium text-foreground">9 {t("header.daysRemaining")}</span>
            <span className="text-muted-foreground">{"·"}</span>
            <span>{t("header.lendingLimit")}: $250,000</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden lg:inline text-xs text-muted-foreground">
            {t("header.keepEarning")}
          </span>
          <button className="rounded-lg bg-destructive px-4 py-1.5 text-xs font-semibold text-destructive-foreground hover:bg-destructive/90 transition-colors">
            {t("header.upgradeNow")}
          </button>
        </div>
      </div>
    </header>
  )
}
