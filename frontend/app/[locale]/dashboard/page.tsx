"use client"

import { useState } from "react"
import { DollarSign, Activity, TrendingUp, Settings } from "lucide-react"
import { Sidebar } from "@/components/dashboard/sidebar"
import { Header } from "@/components/dashboard/header"
import { ProfitCenter } from "@/components/dashboard/profit-center"
import { LiveStatus } from "@/components/dashboard/live-status"
import { TrueROI } from "@/components/dashboard/true-roi"
import { SettingsPage } from "@/components/dashboard/settings"
import { useT } from "@/lib/i18n"
import { DateRangeProvider } from "@/lib/date-range-context"

export default function DashboardPage() {
  const [activePage, setActivePage] = useState("profit-center")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const t = useT()

  return (
    <DateRangeProvider>
    <div className="min-h-screen bg-background">
      <Sidebar
        activePage={activePage}
        onPageChange={setActivePage}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <div
        className={`transition-all duration-300 ${sidebarCollapsed ? "md:ml-16" : "md:ml-56"}`}
      >
        <Header />

        <main className="p-4 pb-20 md:pb-4 lg:p-6">
          {activePage === "profit-center" && <ProfitCenter />}
          {activePage === "live-status" && <LiveStatus />}
          {activePage === "true-roi" && <TrueROI />}
          {activePage === "settings" && <SettingsPage />}
        </main>
      </div>

      <MobileNav activePage={activePage} onPageChange={setActivePage} t={t} />
    </div>
    </DateRangeProvider>
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
    { id: "true-roi", labelKey: "nav.roi", Icon: TrendingUp },
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
