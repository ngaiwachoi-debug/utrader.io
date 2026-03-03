"use client"

import { useState, useEffect } from "react"
import { useSearchParams, useRouter, usePathname } from "next/navigation"
import { useSession } from "next-auth/react"
import { DollarSign, Activity, Settings, CreditCard } from "lucide-react"
import { Sidebar } from "@/components/dashboard/sidebar"
import { Header } from "@/components/dashboard/header"
import { ProfitCenter } from "@/components/dashboard/profit-center"
import { LiveStatus } from "@/components/dashboard/live-status"
import { MarketStatus } from "@/components/dashboard/market-status"
import { TrueROI } from "@/components/dashboard/true-roi"
import { Subscription } from "@/components/dashboard/subscription"
import { ReferralUsdt } from "@/components/dashboard/referral-usdt"
import { Ranking } from "@/components/dashboard/ranking"
import { TerminalView } from "@/components/dashboard/terminal-view"
import { SettingsPage } from "@/components/dashboard/settings"
import { MobileMenuDrawer } from "@/components/dashboard/mobile-menu-drawer"
import { useT } from "@/lib/i18n"
import { DateRangeProvider } from "@/lib/date-range-context"
import { CurrentUserProvider, useCurrentUserId } from "@/lib/current-user-context"
import { BotStatusProvider } from "@/lib/bot-status-context"
import { DashboardDataProvider, useDashboardData, useUserStatus } from "@/lib/dashboard-data-context"

function normalizePlanTier(raw: string): string {
  const s = (raw ?? "trial").toString().trim().toLowerCase()
  if (s === "ai ultra") return "ai_ultra"
  return s.replace(/\s+/g, "_")
}

export default function DashboardPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { data: session, status: sessionStatus } = useSession()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  if (!mounted) {
    return (
      <div className="min-h-screen bg-background" suppressHydrationWarning />
    )
  }

  return (
    <CurrentUserProvider>
      <DateRangeProvider>
        <DashboardDataProvider>
          <DashboardLayout searchParams={searchParams} />
        </DashboardDataProvider>
      </DateRangeProvider>
    </CurrentUserProvider>
  )
}

function DashboardLayout({ searchParams }: { searchParams: ReturnType<typeof useSearchParams> | null }) {
  const t = useT()
  const pathname = usePathname()
  const userId = useCurrentUserId()
  const id = userId ?? 0
  const { prefetch } = useDashboardData()
  const userStatus = useUserStatus(id)
  const planTier = normalizePlanTier(userStatus.data?.plan_tier ?? "trial")
  const [activePage, setActivePage] = useState("profit-center")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    if (userId != null) prefetch(userId)
  }, [userId, prefetch])

  useEffect(() => {
    if (searchParams?.get("page") === "subscription") setActivePage("subscription")
  }, [searchParams])

  const handleUpgrade = () => setActivePage("subscription")

  return (
    <div className="min-h-screen bg-background flex flex-col" suppressHydrationWarning>
      <BotStatusProvider onUpgradeClick={handleUpgrade}>
        <Sidebar
          activePage={activePage}
          onPageChange={setActivePage}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          planTier={planTier}
        />

        <div
          className={`transition-all duration-300 flex flex-col flex-1 min-h-0 ${sidebarCollapsed ? "md:ml-16" : "md:ml-56"}`}
        >
          <div className="w-full">
            <Header onUpgradeClick={handleUpgrade} onOpenMobileMenu={() => setMobileMenuOpen(true)} />
          </div>

          <MobileMenuDrawer
            open={mobileMenuOpen}
            onOpenChange={setMobileMenuOpen}
            activePage={activePage}
            onPageChange={setActivePage}
            t={t}
            pathname={pathname}
          />

          <main className="p-4 pb-20 md:pb-4 lg:p-6 flex flex-col flex-1 min-h-0">
            {activePage === "profit-center" && <ProfitCenter onUpgradeClick={handleUpgrade} />}
            {activePage === "live-status" && <LiveStatus />}
            {activePage === "market-status" && <MarketStatus />}
            {activePage === "true-roi" && <TrueROI />}
            {activePage === "subscription" && <Subscription />}
            {activePage === "referral-usdt" && <ReferralUsdt />}
            {activePage === "leaderboard" && <Ranking />}
            {activePage === "terminal" && (
              <div className="flex flex-col flex-1 min-h-0">
                <TerminalView />
              </div>
            )}
            {activePage === "settings" && <SettingsPage onUpgradeClick={handleUpgrade} />}
          </main>
        </div>

        <MobileNav activePage={activePage} onPageChange={setActivePage} t={t} />
      </BotStatusProvider>
    </div>
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
    { id: "subscription", labelKey: "sidebar.subscription", Icon: CreditCard },
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
              isActive ? "text-primary" : "text-muted-foreground"
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
