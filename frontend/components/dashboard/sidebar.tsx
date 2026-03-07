"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  DollarSign,
  Activity,
  TrendingUp,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  User,
  BarChart3,
  CreditCard,
  Terminal,
  UserPlus,
  Trophy,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useT } from "@/lib/i18n"
import { signOut } from "next-auth/react"
import { clearBackendTokenCache } from "@/lib/auth"
import { useSession } from "next-auth/react"

interface SidebarProps {
  activePage: string
  onPageChange: (page: string) => void
  collapsed: boolean
  onToggle: () => void
  planTier?: string
}

const allNavItems = [
  { id: "profit-center", labelKey: "sidebar.profitCenter", icon: DollarSign },
  { id: "live-status", labelKey: "sidebar.liveStatus", icon: Activity },
  { id: "market-status", labelKey: "sidebar.marketStatus", icon: BarChart3 },
  { id: "true-roi", labelKey: "sidebar.trueRoi", icon: TrendingUp },
  { id: "subscription", labelKey: "sidebar.subscription", icon: CreditCard },
  { id: "referral-usdt", labelKey: "sidebar.referralUsdt", icon: UserPlus },
  { id: "leaderboard", labelKey: "sidebar.leaderboard", icon: Trophy },
  { id: "terminal", labelKey: "sidebar.terminal", icon: Terminal },
  { id: "settings", labelKey: "sidebar.settings", icon: Settings },
]

export function Sidebar({ activePage, onPageChange, collapsed, onToggle, planTier = "trial" }: SidebarProps) {
  const navItems = allNavItems
  const t = useT()
  const router = useRouter()
  const { data: session, status } = useSession()
  const signedIn = status === "authenticated" && !!session?.user

  const handleLogout = () => {
    clearBackendTokenCache()
    signOut({ callbackUrl: "/" }).then(() => router.refresh())
  }

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 hidden h-screen flex-col border-r border-border bg-sidebar transition-all duration-300 md:flex",
        collapsed ? "w-16" : "w-56"
      )}
    >
      {/* Logo: top when expanded; moves to bottom when collapsed */}
      <div className="flex h-14 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-2 overflow-hidden">
          {!collapsed && (
            <>
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary">
                <TrendingUp className="h-4 w-4 text-primary-foreground" />
              </div>
              <span className="text-sm font-semibold text-foreground whitespace-nowrap">
                bifinexbot<span className="text-primary">.com</span>
              </span>
            </>
          )}
        </div>
        <button
          onClick={onToggle}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground hover:text-foreground transition-colors"
          aria-label={collapsed ? t("sidebar.expandSidebar") : t("sidebar.collapseSidebar")}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Nav Items */}
      <nav className="flex-1 px-2 py-4">
        <ul className="flex flex-col gap-1" role="menu">
          {navItems.map((item) => {
            const isActive = activePage === item.id
            return (
              <li key={item.id} role="menuitem">
                <button
                  onClick={() => onPageChange(item.id)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                    isActive
                      ? "bg-primary text-primary-foreground shadow-md shadow-primary/20"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {!collapsed && <span className="whitespace-nowrap">{t(item.labelKey)}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* User Area: when collapsed, logo appears here above avatar */}
      <div className="border-t border-border p-3">
        {collapsed && (
          <div className="mb-3 flex justify-center">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary">
              <TrendingUp className="h-4 w-4 text-primary-foreground" />
            </div>
          </div>
        )}
        {signedIn ? (
          <>
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-orange-500 text-sm font-bold text-foreground">
                J
              </div>
              {!collapsed && (
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{session?.user?.name ?? session?.user?.email ?? t("Common.user")}</p>
                  <p className="truncate text-xs text-muted-foreground">{t("sidebar.googleAccount")}</p>
                </div>
              )}
            </div>
            {!collapsed && (
              <button
                onClick={handleLogout}
                className="mt-3 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
              >
                <LogOut className="h-4 w-4" />
                <span>{t("sidebar.logout")}</span>
              </button>
            )}
          </>
        ) : (
          !collapsed && (
            <Link
              href="/login"
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-primary hover:bg-primary/10 transition-colors"
            >
              <User className="h-4 w-4" />
              <span>{t("sidebar.signIn")}</span>
            </Link>
          )
        )}
      </div>
    </aside>
  )
}
