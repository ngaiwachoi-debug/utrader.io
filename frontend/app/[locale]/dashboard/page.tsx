"use client"

import { useState, useEffect, useRef } from "react"
import { useSearchParams, useRouter, usePathname } from "next/navigation"
import { useSession } from "next-auth/react"
import { DollarSign, Activity, Settings, CreditCard, Trophy } from "lucide-react"
import { toast } from "sonner"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { useT } from "@/lib/i18n"
import { DateRangeProvider } from "@/lib/date-range-context"
import { CurrentUserProvider, useCurrentUserId } from "@/lib/current-user-context"
import { BotStatusProvider } from "@/lib/bot-status-context"
import { DashboardDataProvider, useDashboardData, useUserStatus, useBotStats } from "@/lib/dashboard-data-context"

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
  const router = useRouter()
  const userId = useCurrentUserId()
  const id = userId ?? 0
  const { prefetch, getUserStatus, getWallets, getTokenBalance } = useDashboardData()
  const userStatus = useUserStatus(id)
  const planTier = normalizePlanTier(userStatus.data?.plan_tier ?? "trial")
  const [activePage, setActivePage] = useState("profit-center")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [paymentReturnStatus, setPaymentReturnStatus] = useState<"success" | "cancel" | null>(null)
  const [apiKeyPopupDismissed, setApiKeyPopupDismissed] = useState(false)
  const paymentProcessedRef = useRef(false)
  const prefetchedUserIdRef = useRef<number | null>(null)
  const botStats = useBotStats(id)
  const showApiKeyPopup = !apiKeyPopupDismissed && botStats.data != null && !botStats.data.has_api_keys && userId != null

  useEffect(() => {
    if (userId != null && prefetchedUserIdRef.current !== userId) {
      prefetchedUserIdRef.current = userId
      prefetch(userId)
    }
  }, [userId, prefetch])

  useEffect(() => {
    const page = searchParams?.get("page")
    if (page === "subscription") setActivePage("subscription")
    if (page === "settings") setActivePage("settings")
  }, [searchParams])

  useEffect(() => {
    const sub = searchParams?.get("subscription")
    const tokens = searchParams?.get("tokens")
    const isSuccess = sub === "success" || tokens === "success"
    const isCancel = sub === "cancel"
    
    if (!isSuccess && !isCancel) return
    if (paymentProcessedRef.current) return

    const clearUrl = () => {
      const next = new URLSearchParams(searchParams?.toString() ?? "")
      next.delete("subscription")
      next.delete("tokens")
      const q = next.toString()
      router.replace(pathname + (q ? `?${q}` : ""))
    }

    if (isSuccess) {
      if (userId == null) return
      paymentProcessedRef.current = true
      ;(async () => {
        await Promise.all([
          getUserStatus(id).refetch(),
          getWallets(id).refetch(),
          getTokenBalance(id).refetch(),
        ])
        toast.success(t("payment.successToast"))
        setPaymentReturnStatus("success")
        clearUrl()
      })()
      return
    }

    if (isCancel) {
      paymentProcessedRef.current = true
      toast.info(t("payment.notCompletedToast"))
      setPaymentReturnStatus("cancel")
      clearUrl()
    }
  }, [searchParams?.get("subscription"), searchParams?.get("tokens"), userId, pathname, id, getUserStatus, getWallets, getTokenBalance, router, searchParams, t])

  const handleUpgrade = () => setActivePage("subscription")

  return (
    <div className="min-h-screen bg-background" suppressHydrationWarning>
      <BotStatusProvider onUpgradeClick={handleUpgrade} onSettingsClick={() => setActivePage("settings")}>
        <Sidebar
          activePage={activePage}
          onPageChange={setActivePage}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          planTier={planTier}
        />

        <div
          className={`transition-all duration-300 ${sidebarCollapsed ? "md:ml-16" : "md:ml-56"}`}
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

          <main className="p-4 pb-20 pt-6 md:pb-6 md:pt-8 lg:p-8 lg:pb-8">
            {activePage === "profit-center" && <ProfitCenter onUpgradeClick={handleUpgrade} />}
            {activePage === "live-status" && <LiveStatus />}
            {activePage === "market-status" && <MarketStatus />}
            {activePage === "true-roi" && <TrueROI planTier={planTier} onUpgradeClick={handleUpgrade} />}
            {activePage === "subscription" && <Subscription />}
            {activePage === "referral-usdt" && <ReferralUsdt />}
            {activePage === "leaderboard" && <Ranking />}
            {activePage === "terminal" && <TerminalView />}
            {activePage === "settings" && <SettingsPage onUpgradeClick={handleUpgrade} />}
          </main>
        </div>

        <MobileNav activePage={activePage} onPageChange={setActivePage} t={t} />

        <Dialog open={showApiKeyPopup} onOpenChange={(open) => { if (!open) setApiKeyPopupDismissed(true) }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("apiKeyPopup.title")}</DialogTitle>
              <DialogDescription>{t("apiKeyPopup.description")}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                onClick={() => {
                  setApiKeyPopupDismissed(true)
                  const params = new URLSearchParams(searchParams?.toString() ?? "")
                  params.set("page", "settings")
                  params.set("tab", "api-keys")
                  router.push(`${pathname}?${params.toString()}`)
                }}
              >
                {t("apiKeyPopup.button")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={paymentReturnStatus === "success"} onOpenChange={(open) => !open && setPaymentReturnStatus(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("payment.successTitle")}</DialogTitle>
              <DialogDescription>{t("payment.successDescription")}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button onClick={() => setPaymentReturnStatus(null)}>{t("Common.ok")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={paymentReturnStatus === "cancel"} onOpenChange={(open) => !open && setPaymentReturnStatus(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("payment.notCompletedTitle")}</DialogTitle>
              <DialogDescription>
                {t("payment.notCompletedDescription")}
                <span className="mt-2 block text-foreground">{t("payment.notCompletedMarketing")}</span>
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPaymentReturnStatus(null)}>
                {t("Common.close")}
              </Button>
              <Button
                onClick={() => {
                  setPaymentReturnStatus(null)
                  setActivePage("subscription")
                }}
              >
                {t("payment.completePurchase")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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
    { id: "leaderboard", labelKey: "sidebar.leaderboard", Icon: Trophy },
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
