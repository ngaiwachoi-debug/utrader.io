"use client"

import { useState, useEffect } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import { useSession } from "next-auth/react"
import { DollarSign, Activity, TrendingUp, Settings, BarChart3, CreditCard, Terminal, UserPlus } from "lucide-react"
import { Sidebar } from "@/components/dashboard/sidebar"
import { Header } from "@/components/dashboard/header"
import { ProfitCenter } from "@/components/dashboard/profit-center"
import { LiveStatus } from "@/components/dashboard/live-status"
import { MarketStatus } from "@/components/dashboard/market-status"
import { TrueROI } from "@/components/dashboard/true-roi"
import { Subscription } from "@/components/dashboard/subscription"
import { ReferralUsdt } from "@/components/dashboard/referral-usdt"
import { TerminalView } from "@/components/dashboard/terminal-view"
import { SettingsPage } from "@/components/dashboard/settings"
import { useT } from "@/lib/i18n"
import { DateRangeProvider } from "@/lib/date-range-context"
import { CurrentUserProvider } from "@/lib/current-user-context"

const ADMIN_EMAIL = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_ADMIN_EMAIL) || "ngaiwanchoi@gmail.com"

export default function DashboardPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { data: session, status: sessionStatus } = useSession()
  const [activePage, setActivePage] = useState("profit-center")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mounted, setMounted] = useState(false)
  const t = useT()

  useEffect(() => setMounted(true), [])

  useEffect(() => {
    if (!mounted || sessionStatus !== "authenticated" || !session?.user?.email) return
    const email = (session.user.email || "").trim().toLowerCase()
    if (email === ADMIN_EMAIL.trim().toLowerCase()) {
      router.replace("/admin")
    }
  }, [mounted, sessionStatus, session?.user?.email, router])

  useEffect(() => {
    if (searchParams?.get("page") === "subscription") setActivePage("subscription")
  }, [searchParams])

  if (!mounted) {
    return (
      <div className="min-h-screen bg-background" suppressHydrationWarning />
    )
  }

  return (
    <CurrentUserProvider>
    <DateRangeProvider>
    <div className="min-h-screen bg-background" suppressHydrationWarning>
      <Sidebar
        activePage={activePage}
        onPageChange={setActivePage}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <div
        className={`transition-all duration-300 ${sidebarCollapsed ? "md:ml-16" : "md:ml-56"}`}
      >
        <Header onUpgradeClick={() => setActivePage("subscription")} />

        <main className="p-4 pb-20 md:pb-4 lg:p-6">
          {activePage === "profit-center" && <ProfitCenter onUpgradeClick={() => setActivePage("subscription")} />}
          {activePage === "live-status" && <LiveStatus />}
          {activePage === "market-status" && <MarketStatus />}
          {activePage === "true-roi" && <TrueROI />}
          {activePage === "subscription" && <Subscription />}
          {activePage === "referral-usdt" && <ReferralUsdt />}
          {activePage === "terminal" && <TerminalView />}
          {activePage === "settings" && <SettingsPage />}
        </main>
      </div>

      <MobileNav activePage={activePage} onPageChange={setActivePage} t={t} />
    </div>
    </DateRangeProvider>
    </CurrentUserProvider>
  )
}

function MobileNav({
  activePage,
  onPageChange,
  t,
}: {
  activePage: string
  onPageChange: (page: string) => void
  t: (key: string) => string
}) {
  const items = [
    { id: "profit-center", labelKey: "nav.profit", Icon: DollarSign },
    { id: "live-status", labelKey: "nav.live", Icon: Activity },
    { id: "market-status", labelKey: "sidebar.marketStatus", Icon: BarChart3 },
    { id: "true-roi", labelKey: "nav.roi", Icon: TrendingUp },
    { id: "subscription", labelKey: "sidebar.subscription", Icon: CreditCard },
    { id: "referral-usdt", labelKey: "sidebar.referralUsdt", Icon: UserPlus },
    { id: "terminal", labelKey: "sidebar.terminal", Icon: Terminal },
    { id: "settings", labelKey: "nav.settings", Icon: Settings },
  ]

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-border bg-card/95 backdrop-blur-md py-2 md:hidden" role="navigation" aria-label="Mobile navigation">
      {items.map((item) => {
        const isActive = activePage === item.id
        return (
          <button
            key={item.id}
            onClick={() => onPageChange(item.id)}
            className={`flex flex-col items-center gap-0.5 px-3 py-1.5 text-xs font-medium transition-colors ${
              isActive ? "text-emerald" : "text-muted-foreground"
            }`}
          >
            <item.Icon className="h-4 w-4" />
            <span>{t(item.labelKey)}</span>
          </button>
        )
      })}
    </nav>
  )
}
