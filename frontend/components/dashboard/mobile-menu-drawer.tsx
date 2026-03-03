"use client"

import { useRouter } from "next/navigation"
import { signOut } from "next-auth/react"
import { DollarSign, Activity, BarChart3, TrendingUp, CreditCard, UserPlus, Trophy, Terminal, Settings, Sun, Moon, Globe, LogOut } from "lucide-react"
import { useTheme } from "next-themes"
import { useLanguage } from "@/lib/i18n"
import { clearBackendTokenCache } from "@/lib/auth"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

// Same order as sidebar: Profit Center → Live Status → Market Status → True ROI → Subscription → Referral & USDT → Ranking → Terminal → Settings
const DRAWER_NAV_ITEMS = [
  { id: "profit-center", labelKey: "sidebar.profitCenter", Icon: DollarSign },
  { id: "live-status", labelKey: "sidebar.liveStatus", Icon: Activity },
  { id: "market-status", labelKey: "sidebar.marketStatus", Icon: BarChart3 },
  { id: "true-roi", labelKey: "sidebar.trueRoi", Icon: TrendingUp },
  { id: "subscription", labelKey: "sidebar.subscription", Icon: CreditCard },
  { id: "referral-usdt", labelKey: "sidebar.referralUsdt", Icon: UserPlus },
  { id: "leaderboard", labelKey: "sidebar.leaderboard", Icon: Trophy },
  { id: "terminal", labelKey: "sidebar.terminal", Icon: Terminal },
  { id: "settings", labelKey: "sidebar.settings", Icon: Settings },
] as const

type MobileMenuDrawerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  activePage: string
  onPageChange: (page: string) => void
  t: (key: string) => string
  pathname: string | null
}

export function MobileMenuDrawer({
  open,
  onOpenChange,
  activePage,
  onPageChange,
  t,
  pathname,
}: MobileMenuDrawerProps) {
  const router = useRouter()
  const { setTheme, resolvedTheme } = useTheme()
  const { language, setLanguage } = useLanguage()
  const isDark = resolvedTheme === "dark"

  const handleNavClick = (id: string) => {
    onPageChange(id)
    onOpenChange(false)
  }

  const handleLocaleChange = (value: string) => {
    const locale = value as "en" | "zh" | "ko" | "ru" | "de"
    setLanguage(locale)
    const path = pathname ?? "/dashboard"
    const localeRegex = /^\/(en|zh|ko|ru|de)(\/|$)/
    if (localeRegex.test(path)) {
      const withoutLocale = path.replace(/^\/(en|zh|ko|ru|de)/, "") || "/"
      const newPath = `/${locale}${withoutLocale === "/" ? "" : withoutLocale}`
      if (path !== newPath) router.push(newPath)
    }
  }

  const localeLabels: Record<string, string> = { en: "English", zh: "中文", ko: "한국어", ru: "Русский", de: "Deutsch" }

  const handleLogout = () => {
    clearBackendTokenCache()
    signOut({ callbackUrl: "/" }).then(() => router.refresh())
    onOpenChange(false)
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[min(100vw-2rem,320px)] flex flex-col p-0">
        <SheetHeader className="flex flex-row items-center justify-between border-b border-border px-4 py-3 text-left">
          <SheetTitle className="text-base font-semibold">{t("header.dashboard")}</SheetTitle>
        </SheetHeader>
        <nav className="flex flex-1 flex-col overflow-y-auto p-4" aria-label="Mobile menu">
          {/* All nav items in sidebar order */}
          <div className="flex flex-col gap-0.5">
            {DRAWER_NAV_ITEMS.map((item) => {
              const isActive = activePage === item.id
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleNavClick(item.id)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )}
                >
                  <item.Icon className="h-4 w-4 shrink-0" />
                  {t(item.labelKey)}
                </button>
              )
            })}
          </div>

          {/* Theme: sun / moon toggle like reference image */}
          <div className="mt-6 flex items-center justify-between gap-3 rounded-lg border border-border bg-secondary/30 px-3 py-2.5">
            <span className="flex items-center gap-2 text-sm font-medium text-foreground">
              {t("header.theme")}
            </span>
            <div className="flex items-center rounded-lg bg-background p-0.5 shadow-inner ring-1 ring-border">
              <button
                type="button"
                onClick={() => setTheme("light")}
                className={cn(
                  "flex items-center justify-center rounded-md p-1.5 transition-colors",
                  !isDark ? "bg-amber-400/90 text-black shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
                aria-label={t("header.themeLight")}
              >
                <Sun className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setTheme("dark")}
                className={cn(
                  "flex items-center justify-center rounded-md p-1.5 transition-colors",
                  isDark ? "bg-slate-600 text-white shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
                aria-label={t("header.themeDark")}
              >
                <Moon className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Language */}
          <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-border bg-secondary/30 px-3 py-2.5">
            <span className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Globe className="h-4 w-4 shrink-0 text-muted-foreground" />
              {localeLabels[language] ?? "English"}
            </span>
            <Select value={language} onValueChange={handleLocaleChange}>
              <SelectTrigger className="w-[120px] border-border bg-background text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="zh">中文</SelectItem>
                <SelectItem value="ko">한국어</SelectItem>
                <SelectItem value="ru">Русский</SelectItem>
                <SelectItem value="de">Deutsch</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Log out */}
          <button
            type="button"
            onClick={handleLogout}
            className="mt-6 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            {t("header.logout")}
          </button>
        </nav>
      </SheetContent>
    </Sheet>
  )
}
