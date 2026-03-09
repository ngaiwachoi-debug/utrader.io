"use client"

import { useState } from "react"
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
import { signIn, signOut } from "next-auth/react"
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

  const userInitial = session?.user?.name
    ? session.user.name.charAt(0).toUpperCase()
    : session?.user?.email?.charAt(0).toUpperCase() ?? "U"

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 hidden h-screen flex-col border-r border-border bg-sidebar transition-all duration-300 md:flex",
        collapsed ? "w-16" : "w-58"
      )}
    >
      {/* Logo header */}
      <div className="flex h-16 items-center justify-between border-b border-border px-3">
        <div className="flex items-center gap-2.5 overflow-hidden min-w-0">
          <img 
            src="/logo.png" 
            alt="LendFinex logo" 
            className="h-8 w-8 shrink-0 object-contain logo-no-bg"
          />
          {!collapsed && (
            <span className="text-sm font-bold text-sidebar-foreground whitespace-nowrap truncate">
              LendFinex
            </span>
          )}
        </div>
        <button
          onClick={onToggle}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent/10 hover:text-foreground transition-colors"
          aria-label={collapsed ? t("sidebar.expandSidebar") : t("sidebar.collapseSidebar")}
        >
          {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Nav Items */}
      <nav className="flex-1 px-2 py-3 overflow-y-auto">
        <ul className="flex flex-col gap-0.5" role="menu">
          {navItems.map((item) => {
            const isActive = activePage === item.id
            return (
              <li key={item.id} role="menuitem">
                <button
                  onClick={() => onPageChange(item.id)}
                  title={collapsed ? t(item.labelKey) : undefined}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                    isActive
                      ? "nav-active-glow text-sidebar-primary"
                      : "text-muted-foreground hover:bg-accent/10 hover:text-foreground"
                  )}
                >
                  <item.icon className={cn("h-4 w-4 shrink-0 transition-colors", isActive ? "text-sidebar-primary" : "")} />
                  {!collapsed && <span className="whitespace-nowrap">{t(item.labelKey)}</span>}
                  {!collapsed && isActive && (
                    <span className="ml-auto h-1.5 w-1.5 rounded-full bg-sidebar-primary shrink-0" />
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* User footer */}
      <div className="border-t border-border p-3 space-y-1">
        {signedIn ? (
          <>
            <div className={cn("flex items-center gap-2.5 rounded-lg px-2 py-2", !collapsed && "pr-3")}>
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-xs font-bold text-primary-foreground shadow-md shadow-primary/20">
                {userInitial}
              </div>
              {!collapsed && (
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-sidebar-foreground">{session?.user?.name ?? session?.user?.email ?? t("Common.user")}</p>
                  <p className="truncate text-xs text-muted-foreground">{t("sidebar.googleAccount")}</p>
                </div>
              )}
            </div>
            {!collapsed && (
              <button
                onClick={handleLogout}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span>{t("sidebar.logout")}</span>
              </button>
            )}
          </>
        ) : (
          !collapsed && (
            <button
              onClick={() => signIn("google", { callbackUrl: "/dashboard" })}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-semibold text-primary hover:bg-primary/10 transition-colors"
            >
              <User className="h-4 w-4" />
              <span>{t("sidebar.signIn")}</span>
            </button>
          )
        )}
      </div>
    </aside>
  )
}
