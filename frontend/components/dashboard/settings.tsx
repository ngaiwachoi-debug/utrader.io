"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter, usePathname } from "next/navigation"
import { toast } from "sonner"
import { useSession } from "next-auth/react"
import { useT } from "@/lib/i18n"
import {
  DollarSign,
  Clock,
  Calendar,
  Link2,
  Lock,
  Eye,
  EyeOff,
  ExternalLink,
  Bell,
  Mail,
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
} from "lucide-react"
import { useCurrentUserId } from "@/lib/current-user-context"
import { getBackendToken } from "@/lib/auth"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type SettingsTab = "lending" | "notifications" | "api-keys" | "community"

export function SettingsPage() {
  const t = useT()
  const userId = useCurrentUserId()
  const { data: session, status } = useSession()
  const signedIn = status === "authenticated" && !!session?.user
  const [activeTab, setActiveTab] = useState<SettingsTab>("lending")
  const [showSecret, setShowSecret] = useState(false)
  const [enableLending, setEnableLending] = useState(true)
  const [customLimit, setCustomLimit] = useState(false)
  const [darkMode, setDarkMode] = useState(true)
  const [dailyEmail, setDailyEmail] = useState(false)

  const [planTier, setPlanTier] = useState<string>("Trial User")
  const [planName, setPlanName] = useState<string>("Expert Plan")
  const [lendingLimit, setLendingLimit] = useState<number>(250000)
  const [rebalanceMinutes, setRebalanceMinutes] = useState<number>(3)
  const [tokensRemaining, setTokensRemaining] = useState<number | null>(null)
  const [tokensUsed, setTokensUsed] = useState<number | null>(null)
  const [initialTokenCredit, setInitialTokenCredit] = useState<number | null>(null)
  const [usedAmount, setUsedAmount] = useState<number>(0)
  const [trialRemainingDays, setTrialRemainingDays] = useState<number | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)

  useEffect(() => {
    if (userId == null) {
      setPlanTier("Trial User")
      setPlanName("Expert Plan")
      setLendingLimit(250000)
      setRebalanceMinutes(3)
      setTrialRemainingDays(null)
      setStatusError(null)
      return
    }
    const fetchUserStatus = async () => {
      setStatusError(null)
      try {
        const token = await getBackendToken()
        const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
        const res = await fetch(`${API_BASE}/user-status/${userId}`, { credentials: "include", headers })
        if (!res.ok) {
          setStatusError(t("dashboard.apiUnreachable"))
          return
        }
        const data = await res.json()

        setPlanTier((data.plan_tier ?? "trial").toUpperCase() + " User")
        const tier = (data.plan_tier ?? "trial").toLowerCase()
        if (tier === "pro") setPlanName("Pro Plan")
        else if (tier === "expert") setPlanName("Expert Plan")
        else if (tier === "guru") setPlanName("Guru Plan")
        else setPlanName("Trial Plan")

        setLendingLimit(Number(data.lending_limit) ?? 0)
        setRebalanceMinutes(Number(data.rebalance_interval) ?? 0)
        const trd = data.trial_remaining_days
        setTrialRemainingDays(typeof trd === "number" ? trd : trd != null ? Number(trd) : null)
        const tr = data.tokens_remaining
        setTokensRemaining(typeof tr === "number" ? tr : tr != null ? Number(tr) : null)
        const tu = data.tokens_used
        setTokensUsed(typeof tu === "number" ? tu : tu != null ? Number(tu) : null)
        const itc = data.initial_token_credit
        setInitialTokenCredit(typeof itc === "number" ? itc : itc != null ? Number(itc) : null)
        setUsedAmount(Number(data.used_amount) ?? 0)
      } catch (e) {
        console.error("Failed to fetch user status", e)
        setStatusError(t("dashboard.apiUnreachable"))
      }
    }
    fetchUserStatus()
  }, [userId, t])

  const tabs: { id: SettingsTab; labelKey: string }[] = [
    { id: "lending", labelKey: "settings.tabs.lending" },
    { id: "notifications", labelKey: "settings.tabs.notifications" },
    { id: "api-keys", labelKey: "settings.tabs.apiKeys" },
    { id: "community", labelKey: "settings.tabs.community" },
  ]

  return (
    <div className="flex flex-col gap-6">
      {/* Page Title */}
      <h1 className="text-2xl font-bold text-foreground">{t("settings.title")}</h1>

      {statusError && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
          {statusError}
        </div>
      )}

      {/* Account & Membership Card */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-foreground">{t("settings.accountMembership")}</h2>
          <p className="text-xs text-muted-foreground">{t("settings.accountMembershipDesc")}</p>
        </div>

        {/* User Info – current session; empty when logged out */}
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
                <span className="rounded-full bg-emerald px-2.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
                  {planTier}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">{session?.user?.email ? `${planName} · ${session.user.email}` : planName}</p>
            </div>
          </div>
        )}

        {/* Plan Details */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
          <div className="flex items-center gap-3">
            <DollarSign className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">{t("settings.lendingLimit")}</p>
              <p className="text-xs text-muted-foreground">
                ${lendingLimit.toLocaleString()}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">{t("settings.rebalancingFrequency")}</p>
              <p className="text-xs text-muted-foreground">{t("settings.everyMinutes", { n: rebalanceMinutes })}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">{t("settings.tokenUsage")}</p>
              <p className="text-xs text-muted-foreground">
                {tokensUsed != null ? `${tokensUsed} tokens used` : "—"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs font-semibold text-foreground">{t("settings.tokensRemaining")}</p>
              <p className="text-xs text-muted-foreground">
                {tokensRemaining != null ? `${Math.round(tokensRemaining)} tokens` : "—"}
              </p>
            </div>
          </div>
        </div>

        <p className="text-xs text-muted-foreground mb-4 max-w-xl">
          {t("settings.tokenUsageExplanation")}
        </p>

        {/* Lending Usage */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-foreground">{t("settings.lendingUsage")}</span>
            <span className="text-xs font-medium text-emerald">
              {lendingLimit > 0 ? `${((usedAmount / lendingLimit) * 100).toFixed(1)}%` : "0%"}
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-secondary">
            <div
              className="h-2 rounded-full bg-emerald transition-all duration-500"
              style={{ width: lendingLimit > 0 ? `${Math.min(100, (usedAmount / lendingLimit) * 100)}%` : "0%" }}
            />
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-xs text-muted-foreground">${usedAmount.toLocaleString()}</span>
            <span className="text-xs text-muted-foreground">${lendingLimit.toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 rounded-lg bg-secondary/50 p-1 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
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
        {activeTab === "lending" && <LendingTab enableLending={enableLending} setEnableLending={setEnableLending} customLimit={customLimit} setCustomLimit={setCustomLimit} darkMode={darkMode} setDarkMode={setDarkMode} />}
        {activeTab === "notifications" && <NotificationsTab dailyEmail={dailyEmail} setDailyEmail={setDailyEmail} />}
        {activeTab === "api-keys" && <ApiKeysTab showSecret={showSecret} setShowSecret={setShowSecret} userId={userId} />}
        {activeTab === "community" && <CommunityTab />}
      </div>
    </div>
  )
}

/* ===================== LENDING TAB ===================== */
function LendingTab({
  enableLending,
  setEnableLending,
  customLimit,
  setCustomLimit,
  darkMode,
  setDarkMode,
}: {
  enableLending: boolean
  setEnableLending: (v: boolean) => void
  customLimit: boolean
  setCustomLimit: (v: boolean) => void
  darkMode: boolean
  setDarkMode: (v: boolean) => void
}) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="text-lg font-semibold text-foreground">Lending Configuration</h3>
        <p className="text-xs text-muted-foreground">Configure your lending settings and risk parameters</p>
      </div>

      {/* Lending Controls */}
      <div>
        <h4 className="text-sm font-semibold text-foreground mb-4">Lending Controls</h4>
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">Enable Lending</p>
              <p className="text-xs text-muted-foreground">Turn on automatic lending for your available funds</p>
            </div>
            <ToggleSwitch checked={enableLending} onChange={setEnableLending} />
          </div>
          <div className="ml-4 flex items-center justify-between border-l-2 border-border pl-4">
            <div>
              <p className="text-sm font-medium text-foreground">Custom Lending Limit</p>
              <p className="text-xs text-muted-foreground">Set a maximum amount for lending operations</p>
            </div>
            <ToggleSwitch checked={customLimit} onChange={setCustomLimit} />
          </div>
        </div>
      </div>

      <div className="h-px bg-border" />

      {/* General Settings */}
      <div>
        <h4 className="text-sm font-semibold text-foreground mb-4">General Settings</h4>
        <div className="flex flex-col gap-4">
          <div>
            <label className="text-sm font-medium text-foreground">Base Currency</label>
            <select className="mt-1 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground outline-none focus:border-emerald/50 focus:ring-1 focus:ring-emerald/50">
              <option>USD</option>
              <option>USDt</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground">Time Zone</label>
            <select className="mt-1 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground outline-none focus:border-emerald/50 focus:ring-1 focus:ring-emerald/50">
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
    </div>
  )
}

/* ===================== NOTIFICATIONS TAB ===================== */
function NotificationsTab({
  dailyEmail,
  setDailyEmail,
}: {
  dailyEmail: boolean
  setDailyEmail: (v: boolean) => void
}) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="text-lg font-semibold text-foreground">Notifications</h3>
        <p className="text-xs text-muted-foreground">Configure how you receive alerts and updates</p>
      </div>

      {/* Daily Email Reports */}
      <div className="rounded-xl border border-border bg-secondary/30 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Mail className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-sm font-semibold text-foreground">Daily Email Reports</p>
              <p className="text-xs text-muted-foreground">Receive a daily summary of your lending performance and key metrics</p>
            </div>
          </div>
          <ToggleSwitch checked={dailyEmail} onChange={setDailyEmail} />
        </div>
      </div>

      {/* Coming Soon Notifications */}
      <div>
        <p className="text-sm font-medium text-muted-foreground mb-3">Additional Notifications (Coming Soon)</p>
        <div className="flex flex-col gap-3">
          {[
            { label: "Bot Errors", icon: AlertTriangle },
            { label: "Low Utilization Rate", icon: TrendingDown },
            { label: "Significant Rate Changes", icon: BarChart3 },
          ].map((item) => (
            <div key={item.label} className="flex items-center justify-between py-2">
              <div className="flex items-center gap-3">
                <item.icon className="h-4 w-4 text-muted-foreground/50" />
                <span className="text-sm text-muted-foreground">{item.label}</span>
              </div>
              <ToggleSwitch checked={false} onChange={() => {}} disabled />
            </div>
          ))}
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button className="rounded-lg bg-emerald px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-emerald-dark transition-colors">
          Save Notification Settings
        </button>
      </div>
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
            throw new Error("Session expired. Please log out and log in again, then try saving your API keys.")
          }
          throw new Error(String(errMsg))
        }
        setBalance(data.balance ?? null)
        setMessage({ type: "success", text: data.message || "Connection successful." })
        setBfxKey("")
        setBfxSecret("")
        setGeminiKey("")
        setHasKeys(true)
        setKeyPreview("••••••••")
        toast.success("Connection Successful", {
          description: data.balance?.total_usd_all != null
            ? `Bitfinex balance: $${Number(data.balance.total_usd_all).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
            : undefined,
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
              const msg = errData.detail || "Could not start bot."
              if (startRes.status === 503) toast.warning("Bot queue unavailable", { description: msg })
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
          throw new Error(String(errMsg))
        }
        setBalance(data.balance ?? null)
        setMessage({ type: "success", text: data.message || "Connection successful." })
        setBfxKey("")
        setBfxSecret("")
        setGeminiKey("")
        setHasKeys(true)
        setKeyPreview("••••••••")
        toast.success("Connection Successful", {
          description: data.balance?.total_usd_all != null
            ? `Bitfinex balance: $${Number(data.balance.total_usd_all).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
            : undefined,
        })
        // Auto-start bot after connecting API keys (dev path) so Terminal shows output
        try {
          const startRes = await fetch(`${API_BASE}/start-bot/${userId}`, { method: "POST", credentials: "include" })
          if (startRes.ok) {
            toast.info("Bot is starting", { description: "Open the Terminal tab to see live output (updates every 10s)." })
          } else {
            const errData = await startRes.json().catch(() => ({}))
            const msg = errData.detail || "Could not start bot."
            if (startRes.status === 503) toast.warning("Bot queue unavailable", { description: msg })
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
      toast.error(isNetworkError ? "Unable to connect" : "Connection failed", { description: errMsg })
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
          <Link2 className="h-5 w-5 text-emerald" />
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
                <span className="rounded-full bg-emerald/20 px-2.5 py-0.5 text-xs font-medium text-emerald">{t("settings.verified")}</span>
              ) : (
                <span className="rounded-full bg-amber-500/20 px-2.5 py-0.5 text-xs font-medium text-amber-500">{t("settings.notTested")}</span>
              )}
              <button
                type="button"
                onClick={handleTestKeys}
                disabled={testingKeys}
                className="flex items-center gap-1.5 rounded-lg bg-emerald px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-emerald-dark disabled:opacity-60"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${testingKeys ? "animate-spin" : ""}`} />
                {testingKeys ? "Testing…" : t("settings.testApiKeys")}
              </button>
              <button
                type="button"
                onClick={handleRemoveKey}
                disabled={removingKey}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-destructive/50 bg-destructive/10 text-destructive hover:bg-destructive/20 disabled:opacity-60"
                aria-label={t("settings.removeKey")}
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
              <CheckCircle className="h-16 w-16 text-emerald" />
            </div>
            <p className="text-sm font-medium text-emerald">{t("settings.connectionSuccessful")}</p>
            <p className="text-xs text-muted-foreground">{t("settings.keysVerifiedReady")}</p>
            {testResult.fundingWallet != null && (
              <div className="mt-4 rounded-lg border border-emerald/30 bg-emerald/10 p-4 flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-emerald shrink-0" />
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
      <div className="flex items-center justify-between rounded-lg border border-emerald/30 bg-emerald/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full border border-emerald/30">
            <span className="h-2 w-2 rounded-full bg-emerald"></span>
          </span>
          <Lock className="h-3.5 w-3.5 text-emerald" />
          <span className="text-xs text-foreground">
            Read-only access {"·"} Your funds stay secure
          </span>
        </div>
        <a href="#" className="text-xs font-medium text-emerald hover:text-emerald-light transition-colors">
          {"Need help? \u2192"}
        </a>
      </div>

      {/* Update API Keys (Image 3) */}
      <div className="flex flex-col gap-4">
        <h4 className="text-sm font-semibold text-foreground">{hasKeys ? t("settings.updateApiKeys") : "Add API Keys"}</h4>
        <div>
          <label className="text-sm font-semibold text-foreground">API Key</label>
          <input
            type="text"
            value={bfxKey}
            onChange={(e) => setBfxKey(e.target.value)}
            placeholder="Enter your Bitfinex API Key"
            className="mt-1.5 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-emerald/50 focus:ring-1 focus:ring-emerald/50"
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
              className="w-full rounded-lg border border-border bg-secondary px-3 py-2.5 pr-10 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-emerald/50 focus:ring-1 focus:ring-emerald/50"
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
            className="mt-1.5 w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-emerald/50 focus:ring-1 focus:ring-emerald/50"
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
              <span className="text-emerald">Account History</span>, {" "}
              <span className="text-emerald">Margin Funding</span>, {" "}
              <span className="text-emerald">Wallets</span>, {" "}
              <span className="text-emerald">Settings</span>
            </li>
            <li>{"3. Move funds to "}
              <span className="text-emerald">Funding wallet</span>
            </li>
          </ol>
        </div>
        <a
          href="https://www.bitfinex.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-lg border border-border bg-secondary px-4 py-2.5 text-xs font-medium text-foreground hover:border-emerald/50 transition-colors"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open Bitfinex
        </a>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={loading}
          className="rounded-lg bg-emerald px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-emerald-dark disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Saving…" : "Save API Keys"}
        </button>
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
          <MessageSquare className="h-5 w-5 text-emerald" />
          <h3 className="text-lg font-semibold text-foreground">{"Community & Support"}</h3>
        </div>
        <p className="text-xs text-muted-foreground">Connect with other uTrader.io users and get real-time support</p>
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
          <li><span className="text-emerald font-medium">Get instant support</span> from our team and experienced users</li>
          <li><span className="text-chart-3 font-medium">Share strategies</span> and learn from successful lenders</li>
          <li><span className="text-chart-2 font-medium">Receive updates</span> about new features and market insights</li>
          <li><span className="text-destructive font-medium">Connect with the community</span> with uTrader.io users</li>
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
          <button className="rounded-lg border border-border bg-card px-4 py-2 text-xs font-medium text-foreground hover:border-emerald/50 transition-colors">
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
          <button className="rounded-lg border border-border bg-card px-4 py-2 text-xs font-medium text-foreground hover:border-emerald/50 transition-colors">
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
        <button className="rounded-lg border border-border bg-card px-4 py-2 text-xs font-medium text-foreground hover:border-emerald/50 transition-colors">
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
          ? "bg-emerald"
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
