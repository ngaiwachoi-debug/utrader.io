"use client"

import { useCallback, useEffect, useState, useRef, useMemo } from "react"
import Link from "next/link"
import { useRouter, usePathname, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { useSession } from "next-auth/react"
import { useT } from "@/lib/i18n"
import {
  Calendar,
  Link2,
  Lock,
  Eye,
  EyeOff,
  ExternalLink,
  MessageSquare,
  AlertTriangle,
  TrendingDown,
  BarChart3,
  BookOpen,
  Shield,
  Send,
  Trash2,
  RefreshCw,
  CheckCircle,
  Pencil,
  X,
} from "lucide-react"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useReferralData, useDeductionMultiplier, useTokenBalance, useUserStatus } from "@/lib/dashboard-data-context"
import { getBackendToken } from "@/lib/auth"
import { Spinner } from "@/components/ui/spinner"
import {
  calculateTotalBudget,
  calculateUsedTokens,
  calculateUsagePercentage,
} from "@/lib/calculateTokenUsage"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api-backend"
const TOKEN_BALANCE_POLL_MS = 60_000

type TokenBalanceState = {
  tokens_remaining: number
  total_tokens_added: number
  total_tokens_deducted: number
  last_gross_usd_used?: number
  updated_at?: string | null
}

type TokenAddHistoryEntry = { amount: number; reason: string; created_at: string; detail?: string | null; balance_before?: number | null; balance_after?: number | null }

function tokenAddReasonLabel(reason: string): string {
  const map: Record<string, string> = {
    registration: "Sign-up bonus",
    admin_add: "Admin adjustment",
    admin_bulk_add: "Admin adjustment",
    deposit_usd: "Deposit",
    subscription_monthly: "Subscription",
    subscription_yearly: "Subscription",
    deduction_rollback: "Refund",
    migration_backfill: "Migration",
  }
  return map[reason] ?? reason
}

type SettingsTab = "general" | "notifications" | "api-keys" | "community" | "token-activity"

const INSUFFICIENT_TOKENS_MSG = "Please add tokens to run the bot. A minimum balance of 1 token is required."

type SettingsPageProps = { onUpgradeClick?: () => void }

const VALID_TABS: SettingsTab[] = ["general", "notifications", "api-keys", "community", "token-activity"]

function getTabFromSearchParams(searchParams: ReturnType<typeof useSearchParams> | null): SettingsTab {
  const tab = searchParams?.get("tab")
  if (tab && VALID_TABS.includes(tab as SettingsTab)) return tab as SettingsTab
  return "general"
}

export function SettingsPage({ onUpgradeClick }: SettingsPageProps) {
  const t = useT()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const userId = useCurrentUserId()
  const id = userId ?? 0
  const { data: referralCacheData } = useReferralData(id)
  const deductionMultiplier = useDeductionMultiplier()
  const { data: session, status } = useSession()
  const signedIn = status === "authenticated" && !!session?.user
  const [activeTab, setActiveTab] = useState<SettingsTab>(() => getTabFromSearchParams(searchParams))
  const [showSecret, setShowSecret] = useState(false)
  const [darkMode, setDarkMode] = useState(true)

  // USDT withdrawal address (from referral cache or referral-info API)
  const cachedAddress = referralCacheData?.referralInfo?.usdt_withdraw_address ?? ""
  const [usdtWithdrawAddress, setUsdtWithdrawAddress] = useState<string>("")
  const [usdtAddressSaving, setUsdtAddressSaving] = useState(false)
  const [isEditingUsdtAddress, setIsEditingUsdtAddress] = useState(false)
  const originalUsdtAddressRef = useRef<string>("")
  const usdtAddressInitialized = useRef(false)

  const userStatus = useUserStatus(id)
  const rawTier = (userStatus.data?.plan_tier ?? "trial").toLowerCase()
  const planTier = rawTier.toUpperCase() + " User"
  const planName = rawTier === "pro" ? "Pro Plan"
    : rawTier === "free" ? "Free Plan"
    : rawTier === "ai_ultra" ? "AI Ultra"
    : rawTier === "whales" ? "Whales Plan"
    : rawTier === "expert" ? "Expert Plan"
    : rawTier === "guru" ? "Guru Plan"
    : "Trial Plan"
  const proExpiry = userStatus.data?.pro_expiry ?? null
  const createdAt = userStatus.data?.created_at ?? null

  // Token balance from dashboard-fold (useTokenBalance); no separate request on load.
  const { data: tokenBalanceFromContext, refetch: refetchTokenBalance } = useTokenBalance(id)
  const tokenBalance: TokenBalanceState | null = tokenBalanceFromContext
    ? {
        tokens_remaining: tokenBalanceFromContext.tokens_remaining,
        total_tokens_added: tokenBalanceFromContext.total_tokens_added,
        total_tokens_deducted: tokenBalanceFromContext.total_tokens_deducted,
      }
    : null
  const tokenBalanceLoading = userId != null && tokenBalanceFromContext == null
  const [tokenBalanceError, setTokenBalanceError] = useState<string | null>(null)
  const tokenBalanceIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (userId == null) {
      setTokenBalanceError(null)
      return
    }
  }, [userId])

  // Token balance: poll only on Token activity tab and when tab is visible (reduces server load)
  useEffect(() => {
    if (userId == null || activeTab !== "token-activity") return
    const startPolling = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return
      tokenBalanceIntervalRef.current = setInterval(refetchTokenBalance, TOKEN_BALANCE_POLL_MS)
    }
    const stopPolling = () => {
      if (tokenBalanceIntervalRef.current) {
        clearInterval(tokenBalanceIntervalRef.current)
        tokenBalanceIntervalRef.current = null
      }
    }
    startPolling()
    const onVisibility = () => {
      stopPolling()
      if (document.visibilityState === "visible") startPolling()
    }
    document.addEventListener("visibilitychange", onVisibility)
    return () => {
      document.removeEventListener("visibilitychange", onVisibility)
      stopPolling()
    }
  }, [userId, activeTab, refetchTokenBalance])

  // Prefer referral cache for USDT address to avoid duplicate request when user already opened Referral page
  useEffect(() => {
    const addr = (cachedAddress ?? "").trim()
    if (addr && !usdtAddressInitialized.current) {
      usdtAddressInitialized.current = true
      setUsdtWithdrawAddress(addr)
      originalUsdtAddressRef.current = addr
    }
  }, [cachedAddress])

  useEffect(() => {
    if (userId == null) return
    if (cachedAddress) return
    const fetchRef = async () => {
      try {
        const token = await getBackendToken()
        if (!token) return
        const res = await fetch(`${API_BASE}/api/v1/user/referral-info`, { headers: { Authorization: `Bearer ${token}` } })
        if (res.ok) {
          const data = await res.json()
          const addr = (data.usdt_withdraw_address ?? "").trim()
          setUsdtWithdrawAddress(addr)
          originalUsdtAddressRef.current = addr
          usdtAddressInitialized.current = true
        }
      } catch {
        // ignore
      }
    }
    fetchRef()
  }, [userId, cachedAddress])

  const saveUsdtAddress = async () => {
    const token = await getBackendToken()
    if (!token) return
    setUsdtAddressSaving(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/user/usdt-withdraw-address`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ address: usdtWithdrawAddress.trim() }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        toast.error(typeof data.detail === "string" ? data.detail : "Failed to save address")
        return
      }
      toast.success("USDT withdrawal address saved successfully!")
      originalUsdtAddressRef.current = usdtWithdrawAddress.trim() // Update original ref
      setIsEditingUsdtAddress(false) // Exit edit mode after successful save
    } catch {
      toast.error("Failed to save")
    } finally {
      setUsdtAddressSaving(false)
    }
  }

  // Sync activeTab from URL when user navigates (e.g. "View all" from header popover)
  useEffect(() => {
    const tab = getTabFromSearchParams(searchParams)
    setActiveTab(tab)
  }, [searchParams])

  const tabs: { id: SettingsTab; labelKey: string }[] = [
    { id: "general", labelKey: "settings.tabs.general" },
    { id: "api-keys", labelKey: "settings.tabs.apiKeys" },
    { id: "notifications", labelKey: "settings.tabs.notifications" },
    { id: "community", labelKey: "settings.tabs.community" },
    { id: "token-activity", labelKey: "settings.tabs.tokenActivity" },
  ]

  const handleTabChange = (tabId: SettingsTab) => {
    setActiveTab(tabId)
    const next = new URLSearchParams(searchParams?.toString() ?? "")
    next.set("page", "settings")
    next.set("tab", tabId)
    router.replace(`${pathname ?? ""}?${next.toString()}`, { scroll: false })
  }

  // Calculated token usage (memoized)
  const tokenUsage = useMemo(() => {
    if (tokenBalance == null) return null
    const totalBudget = calculateTotalBudget(tokenBalance.total_tokens_added)
    const used = tokenBalance.total_tokens_deducted
    const pct = calculateUsagePercentage(used, totalBudget)
    return { totalBudget, used, pct, remaining: tokenBalance.tokens_remaining }
  }, [tokenBalance])

  return (
    <div className="flex flex-col gap-6">
      {/* Page Title */}
      <h1 className="text-2xl font-bold text-foreground">{t("settings.title")}</h1>

      {/* Account & Membership Card – restructured: Current Plan, Rebalancing, Token Usage %, Tokens Remaining, Next Renewal */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-foreground">{t("settings.accountMembership")}</h2>
          <p className="text-xs text-muted-foreground">{t("settings.accountMembershipDesc")}</p>
        </div>

        {/* User Info – current session */}
        {signedIn && (session?.user?.name || session?.user?.email) && (
          <div className="flex items-center gap-4 mb-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-orange-500 text-lg font-bold text-foreground">
              {(session?.user?.name || session?.user?.email || "?").charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-semibold text-foreground">
                  {session?.user?.name || session?.user?.email || t("Common.user")}
                </span>
                <span className="rounded-full bg-primary px-2.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
                  {planTier}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">{session?.user?.email ? `${planName} · ${session.user.email}` : planName}</p>
            </div>
          </div>
        )}

        {/* Plan Details: Current Plan, Token Usage %, Tokens Remaining, Registration Date */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
          <div className="flex items-center gap-3">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">Current Plan</p>
              <p className="text-xs text-muted-foreground">{planName}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">{t("settings.tokenUsage")}</p>
              <p className="text-xs text-muted-foreground">
                {tokenUsage != null ? `${Math.round(100 - tokenUsage.pct)}% Remaining` : tokenBalance != null ? "100% Remaining" : "—"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">{t("settings.tokensRemaining")}</p>
              <p className="text-xs text-muted-foreground">
                {tokenUsage != null ? `${Math.round(tokenUsage.remaining)} Tokens` : tokenBalance != null ? `${Math.round(tokenBalance.tokens_remaining)} Tokens` : tokenBalanceLoading ? "…" : "—"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">Registration Date</p>
              <p className="text-xs text-muted-foreground">
                {createdAt ? (() => { try { const d = new Date(createdAt); return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); } catch { return "—"; } })() : "—"}
              </p>
            </div>
          </div>
        </div>

        <p className="text-xs text-muted-foreground mb-4 max-w-xl">
          {t("settings.tokenUsageExplanation", { multiplier: deductionMultiplier })}
        </p>

        {/* Token Usage section (replaces Lending Usage) – progress bar from /api/v1/users/me/token-balance */}
        <div>
          <span className="text-xs font-medium text-foreground">{t("settings.tokenUsageSection")}</span>
          {tokenBalanceError && (
            <p className="mt-2 text-xs text-destructive">{tokenBalanceError}</p>
          )}
          {!tokenBalanceError && tokenBalanceLoading && tokenBalance == null && (
            <div className="mt-2 h-2 w-full rounded bg-secondary animate-pulse" style={{ borderRadius: 4 }} />
          )}
          {!tokenBalanceError && !tokenBalanceLoading && tokenUsage != null && tokenUsage.totalBudget === 0 && (
            <p className="mt-2 text-center text-xs text-muted-foreground">{t("settings.noTokensAvailable")}</p>
          )}
          {!tokenBalanceError && !tokenBalanceLoading && tokenUsage != null && tokenUsage.totalBudget > 0 && (
            <>
              <div className="mt-2 relative w-full h-2 rounded overflow-hidden bg-secondary" style={{ height: 8, borderRadius: 4 }}>
                <div
                  className="absolute inset-y-0 left-0 rounded transition-all duration-500"
                  style={{
                    width: `${Math.min(100, Math.max(0, 100 - tokenUsage.pct))}%`,
                    borderRadius: 4,
                    background:
                      (100 - tokenUsage.pct) >= 50 ? "#10b981" : (100 - tokenUsage.pct) >= 20 ? "#f59e0b" : "#ef4444",
                  }}
                />
                <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white" style={{ textShadow: "0 0 1px rgba(0,0,0,0.5)" }}>
                  {Math.round(100 - tokenUsage.pct)}% Remaining
                </span>
              </div>
              <div className="flex items-center justify-between mt-1.5">
                <span className="text-xs text-muted-foreground">
                  {t("settings.tokensRemainingUsed", { remaining: Math.round(tokenUsage.remaining), used: Math.round(tokenUsage.used) })}
                </span>
                <span className="text-xs text-muted-foreground">
                  {t("settings.totalBudget", { total: Math.round(tokenUsage.totalBudget) })}
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 rounded-lg bg-secondary/50 p-1 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`rounded-md px-4 py-2 text-xs font-medium transition-all ${
              activeTab === tab.id
                ? "bg-card text-foreground shadow-sm border border-border"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="rounded-xl border border-border bg-card p-5">
        {activeTab === "general" && (
          <GeneralTab
            darkMode={darkMode}
            setDarkMode={setDarkMode}
            usdtWithdrawAddress={usdtWithdrawAddress}
            setUsdtWithdrawAddress={setUsdtWithdrawAddress}
            onSaveUsdtAddress={saveUsdtAddress}
            usdtAddressSaving={usdtAddressSaving}
            isEditingUsdtAddress={isEditingUsdtAddress}
            setIsEditingUsdtAddress={setIsEditingUsdtAddress}
            originalUsdtAddress={originalUsdtAddressRef.current}
            setOriginalUsdtAddress={(v: string) => { originalUsdtAddressRef.current = v }}
          />
        )}
        {activeTab === "notifications" && <NotificationsTab />}
        {activeTab === "api-keys" && <ApiKeysTab showSecret={showSecret} setShowSecret={setShowSecret} userId={userId} />}
        {activeTab === "community" && <CommunityTab />}
        {activeTab === "token-activity" && <TokenActivityTab />}
      </div>
    </div>
  )
}

/* ===================== GENERAL TAB (lending controls removed) ===================== */
function GeneralTab({
  darkMode,
  setDarkMode,
  usdtWithdrawAddress,
  setUsdtWithdrawAddress,
  onSaveUsdtAddress,
  usdtAddressSaving,
  isEditingUsdtAddress,
  setIsEditingUsdtAddress,
  originalUsdtAddress,
  setOriginalUsdtAddress,
}: {
  darkMode: boolean
  setDarkMode: (v: boolean) => void
  usdtWithdrawAddress: string
  setUsdtWithdrawAddress: (v: string) => void
  onSaveUsdtAddress: () => Promise<void>
  usdtAddressSaving: boolean
  isEditingUsdtAddress: boolean
  setIsEditingUsdtAddress: (v: boolean) => void
  originalUsdtAddress: string
  setOriginalUsdtAddress: (v: string) => void
}) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="text-lg font-semibold text-foreground">General Settings</h3>
        <p className="text-xs text-muted-foreground">Preferences for the dashboard</p>
      </div>

      <div className="flex flex-col gap-4">
        <div>
          <label className="text-sm font-medium text-foreground">USDT Withdrawal Address</label>
          <p className="text-xs text-muted-foreground mb-1">TRC20 (T...) or ERC20 (0x...). Used for USDT Credit withdrawal requests.</p>
          {usdtWithdrawAddress && !isEditingUsdtAddress ? (
            // View mode: show address as read-only (greyed out)
            <div className="flex gap-2">
              <input
                type="text"
                value={usdtWithdrawAddress}
                readOnly
                className="mt-1 flex-1 rounded-lg border border-border bg-muted/50 px-3 py-2.5 text-sm text-muted-foreground font-mono cursor-not-allowed"
              />
              <button
                type="button"
                onClick={() => {
                  setOriginalUsdtAddress(usdtWithdrawAddress) // Capture current value as snapshot for cancel
                  setIsEditingUsdtAddress(true)
                }}
                className="mt-1 flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium text-foreground hover:bg-secondary transition-colors"
              >
                <Pencil className="w-4 h-4" />
                Edit
              </button>
            </div>
          ) : (
            // Edit mode: show editable input with Save/Cancel buttons
            <div className="flex gap-2">
              <input
                type="text"
                value={usdtWithdrawAddress}
                onChange={(e) => setUsdtWithdrawAddress(e.target.value)}
                placeholder="T... or 0x..."
                className="mt-1 flex-1 rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground font-mono outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50"
              />
              <button
                type="button"
                onClick={onSaveUsdtAddress}
                disabled={usdtAddressSaving}
                className="mt-1 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {usdtAddressSaving ? "Saving…" : "Save"}
              </button>
              {originalUsdtAddress && (
                <button
                  type="button"
                  onClick={() => {
                    setUsdtWithdrawAddress(originalUsdtAddress) // Restore original value
                    setIsEditingUsdtAddress(false)
                  }}
                  disabled={usdtAddressSaving}
                  className="mt-1 flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium text-foreground hover:bg-secondary transition-colors disabled:opacity-50"
                >
                  <X className="w-4 h-4" />
                  Cancel
                </button>
              )}
            </div>
          )}
        </div>
        <div>
          <label className="text-sm font-medium text-foreground">Base Currency</label>
          <select className="mt-1 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50">
            <option>USD</option>
            <option>USDt</option>
          </select>
        </div>
        <div>
          <label className="text-sm font-medium text-foreground">Time Zone</label>
          <select className="mt-1 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50">
            <option>UTC</option>
            <option>EST</option>
            <option>PST</option>
            <option>CET</option>
            <option>JST</option>
          </select>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Dark Mode</p>
            <p className="text-xs text-muted-foreground">Enable dark mode for the dashboard</p>
          </div>
          <ToggleSwitch checked={darkMode} onChange={setDarkMode} />
        </div>
      </div>
    </div>
  )
}

/* ===================== NOTIFICATIONS TAB ===================== */
type NotificationEntry = { id: number; title: string; content?: string | null; type: string; created_at: string }

function NotificationsTab() {
  const t = useT()
  const [notifications, setNotifications] = useState<NotificationEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchNotifications = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const token = await getBackendToken()
      if (!token) {
        setNotifications([])
        return
      }
      const res = await fetch(`${API_BASE}/api/v1/users/me/notifications?limit=50`, {
        credentials: "include",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(t("notifications.error"))
        setNotifications([])
        return
      }
      const data = await res.json()
      setNotifications(Array.isArray(data) ? data : [])
    } catch {
      setError(t("notifications.error"))
      setNotifications([])
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    fetchNotifications()
  }, [fetchNotifications])

  const formatDate = (iso: string) => {
    if (!iso) return "—"
    try {
      const d = new Date(iso)
      if (Number.isNaN(d.getTime())) return "—"
      return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })
    } catch {
      return "—"
    }
  }

  const typeLabel = (type: string) => {
    if (type === "warning") return t("notifications.type.warning")
    if (type === "announcement") return t("notifications.type.announcement")
    return t("notifications.type.info")
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-foreground">{t("notifications.title")}</h3>
          <p className="text-xs text-muted-foreground">{t("notifications.emptyHint")}</p>
        </div>
        <button
          type="button"
          onClick={() => fetchNotifications()}
          disabled={loading}
          className="shrink-0 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50 flex items-center gap-1.5"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          {t("notifications.refresh")}
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Spinner className="h-4 w-4" />
          {t("notifications.loading")}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center justify-between gap-2">
          <span>{error}</span>
          <button type="button" onClick={() => fetchNotifications()} className="rounded-md px-2 py-1 text-xs font-medium bg-destructive/20 hover:bg-destructive/30">
            {t("notifications.retry")}
          </button>
        </div>
      )}

      {!loading && !error && notifications.length === 0 && (
        <p className="py-6 text-sm text-muted-foreground">{t("notifications.empty")}</p>
      )}

      {!loading && !error && notifications.length > 0 && (
        <div className="flex flex-col gap-3 max-h-[400px] overflow-y-auto">
          {notifications.map((n) => (
            <div
              key={n.id}
              className="rounded-xl border border-border bg-secondary/30 p-4 flex flex-col gap-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-foreground line-clamp-1">{n.title}</span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    n.type === "warning"
                      ? "bg-amber-500/20 text-amber-600 dark:text-amber-400"
                      : n.type === "announcement"
                        ? "bg-violet-500/20 text-violet-600 dark:text-violet-400"
                        : "bg-primary/20 text-primary"
                  }`}
                >
                  {typeLabel(n.type)}
                </span>
              </div>
              {n.content && (
                <p className="text-xs text-muted-foreground line-clamp-3">{n.content}</p>
              )}
              <p className="text-[10px] text-muted-foreground">{formatDate(n.created_at)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ===================== API KEYS TAB ===================== */
const BITFINEX_API_SETTINGS_URL = "https://setting.bitfinex.com/api"

function ApiKeysTab({
  showSecret,
  setShowSecret,
  userId,
}: {
  showSecret: boolean
  setShowSecret: (v: boolean) => void
  userId: number | null
}) {
  const t = useT()
  const [apiKeysHelpUrl, setApiKeysHelpUrl] = useState<string>("#")

  useEffect(() => {
    const fetchHelpUrl = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/public/api-keys-help-url`)
        if (res.ok) {
          const data = await res.json()
          setApiKeysHelpUrl(data.url || "#")
        }
      } catch {
        // Keep default "#"
      }
    }
    fetchHelpUrl()
  }, [])
  const router = useRouter()
  const pathname = usePathname()
  const [bfxKey, setBfxKey] = useState("")
  const [bfxSecret, setBfxSecret] = useState("")
  const [geminiKey, setGeminiKey] = useState("")
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [balance, setBalance] = useState<{ total_usd_all?: number; usd_only?: number; per_currency_usd?: Record<string, number> } | null>(null)
  const [hasKeys, setHasKeys] = useState<boolean | null>(null)
  const [keyPreview, setKeyPreview] = useState<string | null>(null)
  const [createdAt, setCreatedAt] = useState<string | null>(null)
  const [lastTestedAt, setLastTestedAt] = useState<string | null>(null)
  const [lastTestBalance, setLastTestBalance] = useState<number | null>(null)
  const [testModalOpen, setTestModalOpen] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; fundingWallet?: number } | null>(null)
  const [testingKeys, setTestingKeys] = useState(false)
  const [removingKey, setRemovingKey] = useState(false)
  const [apiKeyModificationLocked, setApiKeyModificationLocked] = useState(false)

  const clearMessage = () => setMessage(null)
  const isPermissionsError = (text: string) => /missing permission|invalid api key|enable them|bitfinex api settings/i.test(text)

  const loadKeysStatus = async () => {
    const { getBackendToken } = await import("@/lib/auth")
    const token = typeof window !== "undefined" ? await getBackendToken() : null
    if (!token) {
      setHasKeys(null)
      return
    }
    try {
      const res = await fetch(`${API_BASE}/api/keys`, {
        method: "GET",
        credentials: "include",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setHasKeys(!!data.has_keys)
        setKeyPreview(data.key_preview ?? null)
        setCreatedAt(data.created_at ?? null)
        setLastTestedAt(data.last_tested_at ?? null)
        setLastTestBalance(data.last_test_balance != null ? Number(data.last_test_balance) : null)
        setApiKeyModificationLocked(!!data.api_key_modification_locked)
      } else {
        setHasKeys(false)
      }
    } catch {
      setHasKeys(false)
    }
  }

  useEffect(() => {
    loadKeysStatus()
  }, [])

  const handleSave = async () => {
    const key = (bfxKey || "").trim()
    const secret = (bfxSecret || "").trim()
    if (!key || !secret) {
      setMessage({ type: "error", text: "Please enter API Key and API Secret." })
      return
    }
    setLoading(true)
    setMessage(null)
    setBalance(null)
    try {
      const { getBackendToken, clearBackendTokenCache } = await import("@/lib/auth")
      let token = typeof window !== "undefined" ? await getBackendToken() : null
      const allowDev = process.env.NEXT_PUBLIC_ALLOW_DEV_CONNECT === "1"

      if (token) {
        let res = await fetch(`${API_BASE}/api/keys`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ bfx_key: key, bfx_secret: secret, gemini_key: geminiKey || undefined }),
        })
        if (res.status === 401) {
          clearBackendTokenCache()
          token = await getBackendToken()
          if (token) {
            res = await fetch(`${API_BASE}/api/keys`, {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
              body: JSON.stringify({ bfx_key: key, bfx_secret: secret, gemini_key: geminiKey || undefined }),
            })
          }
        }
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          const d = data.detail
          const errMsg = typeof d === "string" ? d : Array.isArray(d) ? (d[0]?.msg ?? JSON.stringify(d)) : (data.message ?? "Invalid Keys")
          if (res.status === 401) {
            const errorMsg = "Session expired. Please log out and log in again, then try saving your API keys."
            toast.error("API Keys Save Failed", { description: errorMsg })
            throw new Error(errorMsg)
          }
          toast.error("API Keys Save Failed", { description: String(errMsg) })
          throw new Error(String(errMsg))
        }
        setBalance(data.balance ?? null)
        setMessage({ type: "success", text: data.message || "Connection successful." })
        setBfxKey("")
        setBfxSecret("")
        setGeminiKey("")
        setHasKeys(true)
        setKeyPreview("••••••••")
        toast.success("API Keys Saved Successfully", {
          description: data.balance?.total_usd_all != null
            ? `Bitfinex balance: $${Number(data.balance.total_usd_all).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
            : "Your API keys have been saved and verified.",
        })
        // Auto-start bot after connecting API keys so Terminal shows output
        if (userId != null) {
          try {
            const startRes = await fetch(`${API_BASE}/start-bot`, {
              method: "POST",
              credentials: "include",
              headers: { Authorization: `Bearer ${token}` },
            })
            if (startRes.ok) {
              toast.info("Bot is starting", { description: "Open the Terminal tab to see live output (updates every 10s)." })
            } else {
              const errData = await startRes.json().catch(() => ({}))
              const msg = typeof errData.detail === "string" ? errData.detail : "Could not start bot."
              const isInsufficient = errData.code === "INSUFFICIENT_TOKENS" || (msg && String(msg).toLowerCase().includes("minimum balance"))
              if (startRes.status === 400 && isInsufficient) {
                toast.warning("Tokens required", {
                  description: INSUFFICIENT_TOKENS_MSG,
                  action: onUpgradeClick ? { label: t("sidebar.subscription"), onClick: onUpgradeClick } : undefined,
                })
              } else if (startRes.status === 503) toast.warning("Bot queue unavailable", { description: msg })
              else if (startRes.status === 402) toast.warning("Bot not started", { description: msg })
            }
          } catch {
            // ignore network errors for start-bot; user can start from Live Status
          }
        }
      } else if (allowDev && userId != null) {
        const res = await fetch(`${API_BASE}/connect-exchange/by-user`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            bfx_key: key,
            bfx_secret: secret,
            gemini_key: geminiKey || undefined,
          }),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          const d = data.detail
          const errMsg = typeof d === "string" ? d : Array.isArray(d) ? (d[0]?.msg ?? JSON.stringify(d)) : (data.message ?? "Invalid Keys")
          toast.error("API Keys Save Failed", { description: String(errMsg) })
          throw new Error(String(errMsg))
        }
        setBalance(data.balance ?? null)
        setMessage({ type: "success", text: data.message || "Connection successful." })
        setBfxKey("")
        setBfxSecret("")
        setGeminiKey("")
        setHasKeys(true)
        setKeyPreview("••••••••")
        toast.success("API Keys Saved Successfully", {
          description: data.balance?.total_usd_all != null
            ? `Bitfinex balance: $${Number(data.balance.total_usd_all).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
            : "Your API keys have been saved and verified.",
        })
        // Auto-start bot after connecting API keys (dev path) so Terminal shows output
        try {
          const startRes = await fetch(`${API_BASE}/start-bot/${userId}`, { method: "POST", credentials: "include" })
          if (startRes.ok) {
            toast.info("Bot is starting", { description: "Open the Terminal tab to see live output (updates every 10s)." })
          } else {
            const errData = await startRes.json().catch(() => ({}))
            const msg = typeof errData.detail === "string" ? errData.detail : "Could not start bot."
            const isInsufficient = errData.code === "INSUFFICIENT_TOKENS" || (msg && String(msg).toLowerCase().includes("minimum balance"))
            if (startRes.status === 400 && isInsufficient) {
              toast.warning("Tokens required", {
                description: INSUFFICIENT_TOKENS_MSG,
                action: onUpgradeClick ? { label: t("sidebar.subscription"), onClick: onUpgradeClick } : undefined,
              })
            } else if (startRes.status === 503) toast.warning("Bot queue unavailable", { description: msg })
            else if (startRes.status === 402) toast.warning("Bot not started", { description: msg })
          }
        } catch {
          // ignore; user can start from Live Status
        }
      } else {
        setMessage({
          type: "error",
          text: "Sign in first to connect your Bitfinex account. Go to Login (or set ALLOW_DEV_CONNECT for dev).",
        })
        setLoading(false)
        return
      }
      setTimeout(clearMessage, 6000)
    } catch (e) {
      const rawMsg = e instanceof Error ? e.message : "Failed to save API keys."
      const isNetworkError = rawMsg === "Failed to fetch" || rawMsg.includes("NetworkError")
      const errMsg = isNetworkError ? t("dashboard.apiUnreachable") : rawMsg
      setMessage({ type: "error", text: errMsg })
      // Only show error toast if not already shown above (to avoid duplicate notifications)
      if (!rawMsg.includes("Session expired") && !rawMsg.includes("Invalid Keys")) {
        toast.error(isNetworkError ? "Unable to connect" : "API Keys Save Failed", { description: errMsg })
      }
      setTimeout(clearMessage, 6000)
    } finally {
      setLoading(false)
    }
  }

  const handleTestKeys = async () => {
    const { getBackendToken } = await import("@/lib/auth")
    const token = typeof window !== "undefined" ? await getBackendToken() : null
    if (!token) {
      setMessage({ type: "error", text: "Sign in first to test API keys." })
      return
    }
    setTestingKeys(true)
    setMessage(null)
    try {
      const res = await fetch(`${API_BASE}/api/keys/test`, {
        method: "POST",
        credentials: "include",
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || "Test failed.")
      }
      setLastTestedAt(new Date().toISOString())
      const bal = data.balance?.total_usd_all ?? undefined
      setLastTestBalance(bal != null ? Number(bal) : null)
      setTestResult({
        success: true,
        fundingWallet: bal != null ? Number(bal) : undefined,
      })
      setTestModalOpen(true)
      loadKeysStatus()
    } catch (e) {
      setMessage({ type: "error", text: e instanceof Error ? e.message : "Test failed." })
    } finally {
      setTestingKeys(false)
    }
  }

  const handleRemoveKey = async () => {
    if (!confirm("Remove stored API keys? You will need to add them again to connect.")) return
    const { getBackendToken } = await import("@/lib/auth")
    const token = typeof window !== "undefined" ? await getBackendToken() : null
    if (!token) {
      setMessage({ type: "error", text: "Sign in first to remove API keys." })
      return
    }
    setRemovingKey(true)
    setMessage(null)
    try {
      const res = await fetch(`${API_BASE}/api/keys`, {
        method: "DELETE",
        credentials: "include",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error("Failed to remove keys.")
      setHasKeys(false)
      setKeyPreview(null)
      setCreatedAt(null)
      setLastTestedAt(null)
      setLastTestBalance(null)
      toast.success("API keys removed")
    } catch (e) {
      setMessage({ type: "error", text: e instanceof Error ? e.message : "Failed to remove." })
    } finally {
      setRemovingKey(false)
    }
  }

  const formatDate = (iso: string | null) => {
    if (!iso) return "—"
    try {
      const d = new Date(iso)
      return d.toLocaleString(undefined, { month: "numeric", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })
    } catch {
      return "—"
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Link2 className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-semibold text-foreground">Connect Bitfinex Account</h3>
        </div>
        <p className="text-xs text-muted-foreground">Enter your read-only API keys to start automated lending. Only one key can be stored.</p>
      </div>

      {/* Current Configuration (Image 3: masked key, Created, status, Test, red bin) */}
      {hasKeys === true && (
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <span className="text-sm font-semibold text-foreground">Current Configuration</span>
            <div className="flex items-center gap-2">
              {lastTestedAt ? (
                <span className="rounded-full bg-primary/20 px-2.5 py-0.5 text-xs font-medium text-primary">{t("settings.verified")}</span>
              ) : (
                <span className="rounded-full bg-amber-500/20 px-2.5 py-0.5 text-xs font-medium text-amber-500">{t("settings.notTested")}</span>
              )}
              <button
                type="button"
                onClick={handleTestKeys}
                disabled={testingKeys}
                className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${testingKeys ? "animate-spin" : ""}`} />
                {testingKeys ? "Testing…" : t("settings.testApiKeys")}
              </button>
              <button
                type="button"
                onClick={handleRemoveKey}
                disabled={removingKey || apiKeyModificationLocked}
                className={`flex h-8 w-8 items-center justify-center rounded-lg border text-destructive disabled:opacity-60 ${
                  apiKeyModificationLocked
                    ? "cursor-not-allowed border-muted bg-muted/50 text-muted-foreground"
                    : "border-destructive/50 bg-destructive/10 hover:bg-destructive/20"
                }`}
                aria-label={t("settings.removeKey")}
                title={apiKeyModificationLocked ? "API key changes disabled during daily fee calculation (10:00–10:30 UTC)" : t("settings.removeKey")}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            API Key: <span className="font-mono text-foreground">{keyPreview ?? "************"}</span>
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("settings.apiKeysCreated")}: {formatDate(createdAt)}
          </p>
          {lastTestedAt && (
            <>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("settings.testedOn", { date: formatDate(lastTestedAt) })}
              </p>
              {lastTestBalance != null && (
                <p className="mt-1 text-xs text-foreground">
                  All required permissions are enabled. Funding wallet contains ~${lastTestBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} available for lending.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {/* Test result modal (Image 4) */}
      {testModalOpen && testResult?.success && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" onClick={() => setTestModalOpen(false)}>
          <div
            className="rounded-xl border border-border bg-card p-6 max-w-md w-full shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-foreground">{t("settings.apiKeyTestResult")}</h3>
            <p className="mt-2 text-sm text-foreground">{t("settings.keysWorkingCorrectly")}</p>
            <div className="flex justify-center my-6">
              <CheckCircle className="h-16 w-16 text-primary" />
            </div>
            <p className="text-sm font-medium text-primary">{t("settings.connectionSuccessful")}</p>
            <p className="text-xs text-muted-foreground">{t("settings.keysVerifiedReady")}</p>
            {testResult.fundingWallet != null && (
              <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-4 flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-primary shrink-0" />
                <span className="text-sm font-medium text-foreground">
                  {t("settings.fundingWalletAvailable", {
                    amount: `$${Number(testResult.fundingWallet).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
                  })}
                </span>
              </div>
            )}
            <p className="mt-4 text-xs text-muted-foreground">
              You're all set! Join our Telegram community for updates and support.
            </p>
            <div className="mt-4 flex gap-3">
              <a
                href="#"
                className="inline-flex items-center gap-2 rounded-lg bg-[#229ED9] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
              >
                <Send className="h-4 w-4" />
                {t("settings.joinTelegram")}
              </a>
              <button
                type="button"
                onClick={() => setTestModalOpen(false)}
                className="rounded-lg border border-border bg-secondary px-4 py-2 text-sm font-medium text-foreground hover:bg-secondary/80"
              >
                {t("settings.close")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Security Notice */}
      <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full border border-primary/30">
            <span className="h-2 w-2 rounded-full bg-primary"></span>
          </span>
          <Lock className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs text-foreground">
            Read-only access {"·"} Your funds stay secure
          </span>
        </div>
        <a 
          href={apiKeysHelpUrl} 
          target={apiKeysHelpUrl.startsWith("http") ? "_blank" : undefined}
          rel={apiKeysHelpUrl.startsWith("http") ? "noopener noreferrer" : undefined}
          className="text-xs font-medium text-primary hover:text-primary transition-colors"
        >
          {"Need help? \u2192"}
        </a>
      </div>

      {/* Update API Keys (Image 3): allow insert when no keys; disable modify when has keys + lock window */}
      <div className="flex flex-col gap-4">
        <h4 className="text-sm font-semibold text-foreground">{hasKeys ? t("settings.updateApiKeys") : "Add API Keys"}</h4>
        {hasKeys && apiKeyModificationLocked && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            API key changes disabled during daily fee calculation (09:55–10:35 UTC). You can add a new key if you have none.
          </p>
        )}
        <div>
          <label className="text-sm font-semibold text-foreground">API Key</label>
          <input
            type="text"
            value={bfxKey}
            onChange={(e) => setBfxKey(e.target.value)}
            placeholder="Enter your Bitfinex API Key"
            disabled={hasKeys === true && apiKeyModificationLocked}
            className="mt-1.5 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 disabled:opacity-60 disabled:cursor-not-allowed"
          />
        </div>
        <div>
          <label className="text-sm font-semibold text-foreground">API Secret</label>
          <div className="relative mt-1.5">
            <input
              type={showSecret ? "text" : "password"}
              value={bfxSecret}
              onChange={(e) => setBfxSecret(e.target.value)}
              placeholder="Enter your Bitfinex API Secret"
              disabled={hasKeys === true && apiKeyModificationLocked}
              className="w-full rounded-lg border border-border bg-secondary px-3 py-2.5 pr-10 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 disabled:opacity-60 disabled:cursor-not-allowed"
            />
            <button
              onClick={() => setShowSecret(!showSecret)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showSecret ? "Hide secret" : "Show secret"}
            >
              {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
        <div>
          <label className="text-sm font-semibold text-foreground">Gemini API Key (optional)</label>
          <input
            type="text"
            value={geminiKey}
            onChange={(e) => setGeminiKey(e.target.value)}
            placeholder="Optional: for AI features"
            disabled={hasKeys === true && apiKeyModificationLocked}
            className="mt-1.5 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 disabled:opacity-60 disabled:cursor-not-allowed"
          />
        </div>
      </div>

      {message && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            message.type === "success"
              ? "border-[#10b981]/30 bg-[#10b981]/10 text-[#10b981]"
              : "border-destructive/30 bg-destructive/10 text-destructive"
          }`}
        >
          {message.text}
          {message.type === "error" && message.text.includes("Sign in") && (
            <span className="block mt-2">
              <Link href="/login" className="font-medium text-foreground underline hover:text-[#10b981]">
                Go to Login →
              </Link>
            </span>
          )}
        </div>
      )}

      {message?.type === "error" && isPermissionsError(message.text) && (
        <div className="rounded-lg border border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <p className="font-semibold flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Permissions required
          </p>
          <p className="mt-1 text-muted-foreground">
            Enable Wallets (Read), Funding (Read/Write), and History (Read) for this API key.
          </p>
          <a
            href={BITFINEX_API_SETTINGS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-2 rounded-lg bg-destructive/20 px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/30 transition-colors"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open Bitfinex API settings
          </a>
        </div>
      )}

      {balance && balance.total_usd_all != null && (
        <div className="rounded-lg border border-[#10b981]/30 bg-[#10b981]/5 px-4 py-3">
          <p className="text-xs font-semibold text-foreground mb-1">Bitfinex balance (fetched)</p>
          <p className="text-2xl font-bold text-[#10b981]">
            ${Number(balance.total_usd_all).toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </p>
          {balance.per_currency_usd && Object.keys(balance.per_currency_usd).length > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              USD: ${Number(balance.per_currency_usd.USD ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
              {" · "}
              USDT: ${Number(balance.per_currency_usd.USDT ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </p>
          )}
        </div>
      )}

      {/* Instructions */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-foreground mb-2">{"Create Bitfinex API Key:"}</p>
          <ol className="flex flex-col gap-1 text-xs text-muted-foreground">
            <li>{"1. Go to Bitfinex \u2192 Settings \u2192 API"}</li>
            <li>{"2. Enable: "}
              <span className="text-primary">Account History</span>, {" "}
              <span className="text-primary">Margin Funding</span>, {" "}
              <span className="text-primary">Wallets</span>, {" "}
              <span className="text-primary">Settings</span>
            </li>
            <li>{"3. Move funds to "}
              <span className="text-primary">Funding wallet</span>
            </li>
          </ol>
        </div>
        <a
          href="https://www.bitfinex.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-lg border border-border bg-secondary px-4 py-2.5 text-xs font-medium text-foreground hover:border-primary/50 transition-colors"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open Bitfinex
        </a>
      </div>

      {/* Save Button: disabled when loading, or when user has keys and lock window is active */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={loading || (hasKeys === true && apiKeyModificationLocked)}
          className="rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Saving…" : "Save API Keys"}
        </button>
      </div>
    </div>
  )
}

/* ===================== TOKEN ACTIVITY TAB ===================== */
type DeductionHistoryEntry = {
  gross_profit: number
  tokens_deducted: number
  tokens_remaining_before: number | null
  tokens_remaining_after: number | null
  total_used_tokens: number | null
  timestamp: string
  account_switch_note: string | null
}

function TokenActivityTab() {
  const t = useT()
  const userId = useCurrentUserId()
  const id = userId ?? 0
  const { data: tokenBalance } = useTokenBalance(id)
  const [addLog, setAddLog] = useState<TokenAddHistoryEntry[]>([])
  const [deductionLog, setDeductionLog] = useState<DeductionHistoryEntry[]>([])
  const [addLoading, setAddLoading] = useState(true)
  const [deductionLoading, setDeductionLoading] = useState(true)

  const fetchTokenActivity = async () => {
    const token = await getBackendToken()
    if (!token) {
      setAddLoading(false)
      setDeductionLoading(false)
      return
    }
    setAddLoading(true)
    setDeductionLoading(true)
    try {
      const [addRes, dedRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/users/me/token-add-history?limit=200`, {
          credentials: "include",
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_BASE}/api/v1/users/me/deduction-history?limit=200`, {
          credentials: "include",
          headers: { Authorization: `Bearer ${token}` },
        }),
      ])
      if (addRes.ok) {
        const data = await addRes.json()
        setAddLog(Array.isArray(data) ? data : [])
      } else {
        setAddLog([])
      }
      if (dedRes.ok) {
        const data = await dedRes.json()
        setDeductionLog(Array.isArray(data) ? data : [])
      } else {
        setDeductionLog([])
      }
    } finally {
      setAddLoading(false)
      setDeductionLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    fetchTokenActivity().then(() => {}, () => {})
    return () => { cancelled = true }
  }, [])

  const formatDate = (iso: string) => {
    if (iso == null || String(iso).trim() === "") return "—"
    try {
      const d = new Date(iso)
      if (Number.isNaN(d.getTime())) return "—"
      return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })
    } catch {
      return "—"
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-foreground">{t("settings.tokenActivityTitle")}</h3>
          <p className="text-xs text-muted-foreground mt-1">{t("settings.tokenActivitySubtitle")}</p>
        </div>
        <button
          type="button"
          onClick={() => fetchTokenActivity()}
          disabled={addLoading || deductionLoading}
          className="shrink-0 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50 flex items-center gap-1.5"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${(addLoading || deductionLoading) ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Authoritative balance summary (same source as Settings) */}
      {tokenBalance != null && (
        <div className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-4 py-2.5 text-xs">
          <span className="text-muted-foreground">
            {t("settings.tokensRemainingUsed", {
              remaining: Math.round(tokenBalance.tokens_remaining),
              used: Math.round(tokenBalance.total_tokens_deducted),
            })}
          </span>
          <span className="text-muted-foreground">
            {t("settings.totalBudget", { total: Math.round(tokenBalance.total_tokens_added) })}
          </span>
        </div>
      )}

      {/* Token add log */}
      <div>
        <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          {t("settings.tokenAddLog")}
        </h4>
        {addLoading ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : addLog.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("settings.noTokenAddHistoryShort")}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border max-h-64">
            <table className="w-full text-xs">
              <thead className="bg-muted/50 sticky top-0">
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 font-medium">Date</th>
                  <th className="text-left py-2 px-3 font-medium">Balance before</th>
                  <th className="text-left py-2 px-3 font-medium">Amount</th>
                  <th className="text-left py-2 px-3 font-medium">Balance after</th>
                  <th className="text-left py-2 px-3 font-medium">Reason</th>
                </tr>
              </thead>
              <tbody>
                {addLog.map((e, i) => (
                  <tr key={i} className="border-b border-border/50 hover:bg-muted/30">
                    <td className="py-2 px-3">{formatDate(e.created_at)}</td>
                    <td className="py-2 px-3">{e.balance_before != null && Number.isFinite(e.balance_before) ? Number(e.balance_before).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</td>
                    <td className="py-2 px-3 font-medium">+{Number(e.amount).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                    <td className="py-2 px-3">{e.balance_after != null && Number.isFinite(e.balance_after) ? Number(e.balance_after).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</td>
                    <td className="py-2 px-3">{e.detail ?? tokenAddReasonLabel(e.reason)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Token deduction log */}
      <div>
        <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
          <TrendingDown className="h-4 w-4 text-muted-foreground" />
          {t("settings.tokenDeductionLog")}
        </h4>
        {deductionLoading ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : deductionLog.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("settings.noDeductionHistory")}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border max-h-64">
            <table className="w-full text-xs">
              <thead className="bg-muted/50 sticky top-0">
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 font-medium">Date</th>
                  <th className="text-left py-2 px-3 font-medium">Balance before</th>
                  <th className="text-left py-2 px-3 font-medium">Gross profit (USD)</th>
                  <th className="text-left py-2 px-3 font-medium">Tokens deducted</th>
                  <th className="text-left py-2 px-3 font-medium">Balance after</th>
                </tr>
              </thead>
              <tbody>
                {deductionLog.map((e, i) => (
                  <tr key={i} className="border-b border-border/50 hover:bg-muted/30">
                    <td className="py-2 px-3">{formatDate(e.timestamp)}</td>
                    <td className="py-2 px-3">{e.tokens_remaining_before != null && Number.isFinite(Number(e.tokens_remaining_before)) ? Number(e.tokens_remaining_before).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</td>
                    <td className="py-2 px-3">{Number(e.gross_profit).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                    <td className="py-2 px-3 font-medium text-destructive">−{Number(e.tokens_deducted).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                    <td className="py-2 px-3">{e.tokens_remaining_after != null ? Number(e.tokens_remaining_after).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

/* ===================== COMMUNITY TAB ===================== */
function CommunityTab() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <MessageSquare className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-semibold text-foreground">{"Community & Support"}</h3>
        </div>
        <p className="text-xs text-muted-foreground">Connect with other bifinexbot.com users and get real-time support</p>
      </div>

      {/* Telegram */}
      <div className="rounded-xl border border-border bg-secondary/30 p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#229ED9]">
            <Send className="h-5 w-5 text-foreground" />
          </div>
          <h4 className="text-base font-semibold text-foreground">Join Our Telegram Community</h4>
        </div>
        <ul className="flex flex-col gap-2 text-sm text-muted-foreground mb-4">
          <li><span className="text-primary font-medium">Get instant support</span> from our team and experienced users</li>
          <li><span className="text-chart-3 font-medium">Share strategies</span> and learn from successful lenders</li>
          <li><span className="text-chart-2 font-medium">Receive updates</span> about new features and market insights</li>
          <li><span className="text-destructive font-medium">Connect with the community</span> with bifinexbot.com users</li>
        </ul>
        <button className="flex items-center gap-2 rounded-lg bg-[#229ED9] px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-[#229ED9]/80 transition-colors">
          <Send className="h-4 w-4" />
          Join Telegram Group
        </button>
      </div>

      {/* Resources */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Learning Hub */}
        <div className="rounded-xl border border-border bg-secondary/30 p-5">
          <div className="flex items-center gap-2 mb-2">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-semibold text-foreground">Learning Hub</h4>
          </div>
          <p className="text-xs text-muted-foreground mb-4">Comprehensive guides and tutorials for crypto lending success</p>
          <button className="rounded-lg border border-border bg-card px-4 py-2 text-xs font-medium text-foreground hover:border-primary/50 transition-colors">
            Explore Guides
          </button>
        </div>

        {/* Security Center */}
        <div className="rounded-xl border border-border bg-secondary/30 p-5">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-semibold text-foreground">Security Center</h4>
          </div>
          <p className="text-xs text-muted-foreground mb-4">Learn about our security measures and best practices</p>
          <button className="rounded-lg border border-border bg-card px-4 py-2 text-xs font-medium text-foreground hover:border-primary/50 transition-colors">
            Security Guide
          </button>
        </div>
      </div>

      {/* Follow on X */}
      <div className="rounded-xl border border-border bg-secondary/30 p-5">
        <div className="flex items-center gap-2 mb-2">
          <svg className="h-4 w-4 text-foreground" viewBox="0 0 24 24" fill="currentColor">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
          </svg>
          <h4 className="text-sm font-semibold text-foreground">Follow us on X</h4>
        </div>
        <p className="text-xs text-muted-foreground mb-4">Follow us for the latest news, updates, and market analysis.</p>
        <button className="rounded-lg border border-border bg-card px-4 py-2 text-xs font-medium text-foreground hover:border-primary/50 transition-colors">
          Follow on X
        </button>
      </div>
    </div>
  )
}

/* ===================== TOGGLE SWITCH ===================== */
function ToggleSwitch({
  checked,
  onChange,
  disabled = false,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => !disabled && onChange(!checked)}
      className={`relative h-6 w-11 rounded-full transition-colors duration-200 ${
        disabled
          ? "bg-secondary cursor-not-allowed opacity-50"
          : checked
          ? "bg-primary"
          : "bg-secondary"
      }`}
    >
      <span
        className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-foreground shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  )
}
