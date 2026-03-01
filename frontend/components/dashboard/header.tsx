"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter, usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import { clearBackendTokenCache, getBackendToken } from "@/lib/auth"
import { Star, Search, Bell, HelpCircle, User, Globe, LogOut, Sun, Moon, AlertTriangle, Coins } from "lucide-react"
import { useTheme } from "next-themes"
import { useLanguage } from "@/lib/i18n"
import { useSession } from "next-auth/react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { useCurrentUserId } from "@/lib/current-user-context"

const API_BACKEND = "/api-backend"

type HeaderProps = { onUpgradeClick?: () => void }

export function Header({ onUpgradeClick }: HeaderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const { data: session, status } = useSession()
  const userId = useCurrentUserId()
  const { language, setLanguage, t } = useLanguage()
  const { setTheme, resolvedTheme } = useTheme()
  const signedIn = status === "authenticated" && !!session?.user
  const isDark = resolvedTheme === "dark"
  const [totalUsdAll, setTotalUsdAll] = useState<number | null>(null)
  const [usdOnly, setUsdOnly] = useState<number | null>(null)
  const [walletsLoading, setWalletsLoading] = useState(true)
  const [tokensRemaining, setTokensRemaining] = useState<number | null>(null)
  const [planTier, setPlanTier] = useState<string | null>(null)
  const [walletDataSource, setWalletDataSource] = useState<"live" | "cache" | null>(null)
  const [walletRateLimited, setWalletRateLimited] = useState(false)

  useEffect(() => {
    if (userId == null) {
      setTotalUsdAll(null)
      setUsdOnly(null)
      setPlanTier(null)
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
          fetch(`${API_BACKEND}/wallets/${userId}`, { credentials: "include", headers }),
          fetch(`${API_BACKEND}/user-status/${userId}`, { credentials: "include", headers }),
        ])
        if (cancelled) return
        try {
          if (walletRes.ok) {
            const data = await walletRes.json().catch(() => ({}))
            setTotalUsdAll(Number(data?.total_usd_all) ?? 0)
            setUsdOnly(Number(data?.usd_only) ?? 0)
            const src = walletRes.headers.get("X-Data-Source")
            setWalletDataSource(src === "cache" ? "cache" : "live")
            setWalletRateLimited(walletRes.headers.get("X-Rate-Limited") === "true")
          } else {
            setTotalUsdAll(null)
            setUsdOnly(null)
            setWalletDataSource(null)
            setWalletRateLimited(false)
          }
        } catch {
          setTotalUsdAll(null)
          setUsdOnly(null)
          setWalletDataSource(null)
          setWalletRateLimited(false)
        }
        try {
          if (statusRes.ok) {
            const statusData = await statusRes.json().catch(() => ({}))
            const tr = statusData?.tokens_remaining
            setTokensRemaining(typeof tr === "number" ? tr : null)
            const tier = statusData?.plan_tier
            setPlanTier(typeof tier === "string" ? tier : null)
          }
        } catch {
          setTokensRemaining(null)
          setPlanTier(null)
        }
      } catch {
        if (!cancelled) {
          setTotalUsdAll(null)
          setUsdOnly(null)
          setPlanTier(null)
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

  const displayTokens =
    tokensRemaining != null
      ? `${Math.round(tokensRemaining)} ${t("header.tokensRemaining")}`
      : "—"
  const tokenLow = tokensRemaining != null && tokensRemaining < 50

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

  return (
    <header className="sticky top-0 z-30 flex w-full flex-col border-b border-border bg-card/80 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between px-4 lg:px-6">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{t("header.dashboard")}</span>
        </div>

        <div className="flex items-center gap-2 lg:gap-3">
          <span className="hidden sm:flex items-center justify-end gap-1.5 text-foreground font-medium min-w-[4rem] text-right text-xs" title={walletRateLimited ? t("header.rateLimited") : walletDataSource === "cache" ? t("header.dataCached") : tokenLow ? t("header.tokenLowRefill") : undefined}>
            {walletsLoading ? <><Spinner className="h-3.5 w-3.5 shrink-0" /><span className="text-muted-foreground">Loading…</span></> : (
              <>
                {tokenLow && (
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500 animate-pulse" aria-hidden />
                )}
                <Coins className={`h-3.5 w-3.5 shrink-0 ${tokenLow ? "text-amber-500 animate-pulse" : "text-emerald"}`} />
                <span className={tokenLow ? "text-amber-600 dark:text-amber-400 font-semibold" : ""}>{displayTokens}</span>
                {tokenLow && (
                  <span className="text-[10px] text-amber-600 dark:text-amber-400 font-medium" title={t("header.tokenLowRefill")}>
                    {t("header.tokenLowRefill")}
                  </span>
                )}
              </>
            )}
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
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-emerald" />
            </button>
            <button className="hidden sm:flex rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors" aria-label={t("header.help")}>
              <HelpCircle className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setTheme(isDark ? "light" : "dark")}
              className="rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
              aria-label={isDark ? t("header.themeLight") : t("header.themeDark")}
              title={isDark ? t("header.themeLight") : t("header.themeDark")}
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
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

      {/* Token / Plan Banner — only for trial and free users */}
      {(planTier === "trial" || planTier === "free") && (
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border bg-card px-4 py-2 lg:px-6">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <Star className="h-3.5 w-3.5 text-yellow-400" />
            <span className="rounded-full bg-emerald px-2.5 py-0.5 text-xs font-semibold text-primary-foreground">
              {tokensRemaining !== null ? `${Math.round(tokensRemaining)} tokens` : "—"}
            </span>
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
      )}
    </header>
  )
}
