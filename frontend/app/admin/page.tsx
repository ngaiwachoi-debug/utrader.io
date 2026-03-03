"use client"

import { useEffect, useState, useCallback } from "react"
import Link from "next/link"
import { useRouter, usePathname } from "next/navigation"
import { useSession, signOut } from "next-auth/react"
import { getBackendToken, clearBackendTokenCache } from "@/lib/auth"
import {
  AlertCircle,
  Copy,
  RefreshCw,
  Users,
  Bot,
  Coins,
  Activity,
  FileText,
  LogOut,
  Download,
  Play,
  Square,
  FileCode,
  Key,
  CreditCard,
  Send,
  Settings,
  UserPlus,
  Wallet,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"

const ADMIN_EMAIL = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_ADMIN_EMAIL) || "ngaiwachoi@gmail.com"

type AdminUser = {
  id: number
  email: string
  plan_tier: string
  rebalance_interval: number
  pro_expiry: string | null
  status: string
  tokens_remaining?: number | null
  bot_status?: string | null
  created_at?: string | null
}

type ApiFailure = {
  id: string
  ts: string
  context: string
  user_id: number | null
  error: string
}

type DeductionEntry = {
  user_id: number
  gross_profit: number
  tokens_deducted: number
  tokens_remaining_before: number
  tokens_remaining_after: number
  timestamp: string
}

type Health = { redis: string; db: string }

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

function BotStatusBadge({ status }: { status: string | null | undefined }) {
  const s = (status ?? "").toLowerCase()
  const stopped = s === "stopped"
  const starting = s === "starting"
  const running = s === "running"
  const error = !stopped && !starting && !running && (s === "error" || s === "failed" || s.length > 0)
  const circleClass = running
    ? "bg-primary"
    : starting
      ? "bg-yellow-500"
      : error
        ? "bg-red-500"
        : "bg-muted-foreground"
  const label = status ?? "—"
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-2 w-2 shrink-0 rounded-full ${circleClass}`} title={label} aria-hidden />
      <span>{label}</span>
    </span>
  )
}

function NotificationFormInline({ backendToken, onSent }: { backendToken: string | null; onSent: () => void }) {
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [targetUserId, setTargetUserId] = useState("")
  const [sending, setSending] = useState(false)
  return (
    <div className="space-y-2 max-w-md">
      <Input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <textarea className="w-full rounded border border-border p-2 text-sm min-h-[60px]" placeholder="Content" value={content} onChange={(e) => setContent(e.target.value)} />
      <Input placeholder="Target user ID (empty = all)" value={targetUserId} onChange={(e) => setTargetUserId(e.target.value)} type="number" />
      <Button size="sm" disabled={!backendToken || sending || !title.trim()} onClick={async () => {
        if (!backendToken) return
        setSending(true)
        const res = await fetch(`${API_BASE}/admin/notifications/send`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${backendToken}` },
          body: JSON.stringify({ title: title.trim(), content: content.trim(), type: "info", target_user_id: targetUserId ? parseInt(targetUserId, 10) : null }),
        })
        setSending(false)
        if (res.ok) { setTitle(""); setContent(""); setTargetUserId(""); onSent(); toast.success("Notification sent") } else toast.error("Send failed")
      }}>Send</Button>
    </div>
  )
}

function AdminSettingsFormInline({ settings, loading, backendToken, onSave }: { settings: { key: string; value: string }[]; loading: boolean; backendToken: string | null; onSave: () => void }) {
  const [local, setLocal] = useState<Record<string, string>>({})
  useEffect(() => { setLocal(Object.fromEntries(settings.map((s) => [s.key, s.value]))) }, [settings])
  const update = (key: string, value: string) => setLocal((p) => ({ ...p, [key]: value }))
  return (
    <div className="space-y-3 max-w-md">
      {settings.map((s) => (
        <div key={s.key} className="flex items-center gap-2">
          <label className="text-sm w-48 shrink-0">{s.key}</label>
          <Input className="flex-1" value={local[s.key] ?? s.value} onChange={(e) => update(s.key, e.target.value)} />
        </div>
      ))}
      <Button size="sm" disabled={!backendToken || loading} onClick={async () => {
        if (!backendToken) return
        const body: Record<string, unknown> = {}
        const v = local.registration_bonus_tokens; if (v !== undefined && v !== "") body.registration_bonus_tokens = parseInt(String(v), 10)
        const v2 = local.min_withdrawal_usdt; if (v2 !== undefined && v2 !== "") body.min_withdrawal_usdt = parseFloat(String(v2))
        const v3 = local.daily_deduction_utc_hour; if (v3 !== undefined && v3 !== "") body.daily_deduction_utc_hour = parseInt(String(v3), 10)
        const v4 = local.bot_auto_start; if (v4 !== undefined && v4 !== "") body.bot_auto_start = v4 === "true"
        const v5 = local.referral_system_enabled; if (v5 !== undefined && v5 !== "") body.referral_system_enabled = v5 === "true"
        const v6 = local.withdrawal_enabled; if (v6 !== undefined && v6 !== "") body.withdrawal_enabled = v6 === "true"
        const v7 = local.maintenance_mode; if (v7 !== undefined && v7 !== "") body.maintenance_mode = v7 === "true"
        const res = await fetch(`${API_BASE}/admin/settings/update`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${backendToken}` }, body: JSON.stringify(body) })
        if (res.ok) { onSave(); toast.success("Settings saved") } else toast.error("Save failed")
      }}>Save</Button>
    </div>
  )
}

const SECTIONS = [
  { id: "users", label: "Users", icon: Users },
  { id: "apiKeys", label: "API Keys", icon: Key },
  { id: "bot", label: "Bot Control", icon: Bot },
  { id: "deduction", label: "Deduction", icon: Coins },
  { id: "usdtCredit", label: "USDT Credit", icon: Wallet },
  { id: "withdrawals", label: "Withdrawals", icon: CreditCard },
  { id: "referrals", label: "Referrals", icon: UserPlus },
  { id: "notifications", label: "Notifications", icon: Send },
  { id: "settings", label: "Settings", icon: Settings },
  { id: "health", label: "Health", icon: Activity },
  { id: "failures", label: "API Failures", icon: AlertCircle },
  { id: "audit", label: "Audit Logs", icon: FileText },
] as const

type SectionId = (typeof SECTIONS)[number]["id"]

export default function AdminPage() {
  const router = useRouter()
  const pathname = usePathname()
  const { data: session, status: sessionStatus } = useSession()
  const [backendToken, setBackendToken] = useState<string | null>(null)
  const [section, setSection] = useState<SectionId>("users")
  const [users, setUsers] = useState<AdminUser[]>([])
  const [userSearch, setUserSearch] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [failures, setFailures] = useState<ApiFailure[]>([])
  const [failuresLoading, setFailuresLoading] = useState(false)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [retryError, setRetryError] = useState<string | null>(null)
  const [deductionLogs, setDeductionLogs] = useState<DeductionEntry[]>([])
  const [deductionLoading, setDeductionLoading] = useState(false)
  const [triggerLoading, setTriggerLoading] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [rollbackUserId, setRollbackUserId] = useState("")
  const [rollbackDate, setRollbackDate] = useState("")
  const [rollbackLoading, setRollbackLoading] = useState(false)
  const [botLogsUserId, setBotLogsUserId] = useState("")
  const [botLogs, setBotLogs] = useState<string[]>([])
  const [botLogsLoading, setBotLogsLoading] = useState(false)
  const [stopCooldownUntil, setStopCooldownUntil] = useState<Record<number, number>>({})
  const [auditLogs, setAuditLogs] = useState<{ ts: string; email: string; action: string; detail: Record<string, unknown> }[]>([])
  const [auditLoading, setAuditLoading] = useState(false)
  const [apiKeys, setApiKeys] = useState<{ user_id: number; email: string; has_keys: boolean; key_masked?: string; last_tested_at?: string }[]>([])
  const [apiKeysLoading, setApiKeysLoading] = useState(false)
  const [usdtRows, setUsdtRows] = useState<{ user_id: number; email: string; usdt_credit: number; total_earned: number; total_withdrawn: number; locked_pending?: number }[]>([])
  const [usdtLoading, setUsdtLoading] = useState(false)
  const [withdrawals, setWithdrawals] = useState<{ id: number; user_id: number; email: string; amount: number; address: string; status: string; created_at: string; processed_at?: string; processed_by?: string; rejection_note?: string | null }[]>([])
  const [withdrawalsLoading, setWithdrawalsLoading] = useState(false)
  const [withdrawalFilter, setWithdrawalFilter] = useState("")
  const [rejectModalWid, setRejectModalWid] = useState<number | null>(null)
  const [rejectNote, setRejectNote] = useState("")
  const [referrals, setReferrals] = useState<{ user_id: number; email: string; referral_code?: string; referrer_id?: number; referrer_email?: string; downline_count: number; referral_earnings: number }[]>([])
  const [referralsLoading, setReferralsLoading] = useState(false)
  const [notifications, setNotifications] = useState<{ id: number; title: string; content?: string; type: string; target_user_id?: number; created_at: string }[]>([])
  const [notificationsLoading, setNotificationsLoading] = useState(false)
  const [adminSettings, setAdminSettings] = useState<{ key: string; value: string }[]>([])
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [bulkTokenInput, setBulkTokenInput] = useState("")
  const [bulkTokenResult, setBulkTokenResult] = useState<{ success_count: number; failed_count: number } | null>(null)
  const [auditFilterAction, setAuditFilterAction] = useState("")
  const [auditFilterEmail, setAuditFilterEmail] = useState("")
  const [deductionStartDate, setDeductionStartDate] = useState("")
  const [deductionEndDate, setDeductionEndDate] = useState("")

  const handleSessionExpired = useCallback(() => {
    clearBackendTokenCache()
    const locale = pathname?.startsWith("/zh") ? "zh" : "en"
    signOut({ callbackUrl: `/${locale}/admin-login` })
    window.location.href = `/${locale}/admin-login`
  }, [signOut, pathname])

  useEffect(() => {
    if (sessionStatus !== "authenticated") return
    getBackendToken().then((t) => setBackendToken(t ?? null))
  }, [sessionStatus])

  const fetchUsers = useCallback(
    async (token: string) => {
      try {
        setLoading(true)
        setError(null)
        const res = await fetch(`${API_BASE}/admin/users`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.status === 401) { handleSessionExpired(); return }
        if (!res.ok) throw new Error("Not authorized")
        const data = await res.json()
        setUsers(data)
      } catch {
        setError("Admin access is restricted to " + ADMIN_EMAIL + ". You are not authorized.")
      } finally {
        setLoading(false)
      }
    },
    [handleSessionExpired]
  )

  useEffect(() => {
    if (!backendToken) return
    void fetchUsers(backendToken)
  }, [backendToken, fetchUsers])

  const fetchFailures = useCallback(async (token: string) => {
    try {
      setFailuresLoading(true)
      const res = await fetch(`${API_BASE}/admin/api-failures?limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.status === 401) { handleSessionExpired(); return }
      if (!res.ok) return
      const data = await res.json()
      setFailures(Array.isArray(data) ? data : [])
    } catch {
      // ignore
    } finally {
      setFailuresLoading(false)
    }
  }, [handleSessionExpired])

  useEffect(() => {
    if (!backendToken) return
    void fetchFailures(backendToken)
    const interval = setInterval(() => fetchFailures(backendToken), 30_000)
    return () => clearInterval(interval)
  }, [backendToken, fetchFailures])

  const fetchDeductionLogs = useCallback(async (token: string) => {
    try {
      setDeductionLoading(true)
      const params = new URLSearchParams({ limit: "100" })
      if (deductionStartDate) params.set("start_date", deductionStartDate)
      if (deductionEndDate) params.set("end_date", deductionEndDate)
      const res = await fetch(`${API_BASE}/admin/deduction/logs?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.status === 401) { handleSessionExpired(); return }
      if (!res.ok) return
      const data = await res.json()
      setDeductionLogs(Array.isArray(data) ? data : [])
    } catch {
      // ignore
    } finally {
      setDeductionLoading(false)
    }
  }, [handleSessionExpired, deductionStartDate, deductionEndDate])

  const fetchHealth = useCallback(async (token: string) => {
    try {
      setHealthLoading(true)
      const res = await fetch(`${API_BASE}/admin/health`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.status === 401) { handleSessionExpired(); return }
      if (!res.ok) return
      const data = await res.json()
      setHealth(data)
    } catch {
      setHealth({ redis: "error", db: "error" })
    } finally {
      setHealthLoading(false)
    }
  }, [handleSessionExpired])

  useEffect(() => {
    if (section === "deduction" && backendToken) void fetchDeductionLogs(backendToken)
  }, [section, backendToken, fetchDeductionLogs])

  useEffect(() => {
    if (section === "health" && backendToken) void fetchHealth(backendToken)
  }, [section, backendToken, fetchHealth])

  const fetchAuditLogs = useCallback(async (token: string) => {
    try {
      setAuditLoading(true)
      const params = new URLSearchParams({ limit: "100" })
      if (auditFilterAction) params.set("action", auditFilterAction)
      if (auditFilterEmail) params.set("email", auditFilterEmail)
      const res = await fetch(`${API_BASE}/admin/audit-logs?${params}`, { headers: { Authorization: `Bearer ${token}` } })
      if (res.status === 401) { handleSessionExpired(); return }
      if (res.ok) setAuditLogs(await res.json())
    } finally {
      setAuditLoading(false)
    }
  }, [auditFilterAction, auditFilterEmail, handleSessionExpired])
  useEffect(() => {
    if (section === "audit" && backendToken) void fetchAuditLogs(backendToken)
  }, [section, backendToken, fetchAuditLogs])

  const fetchApiKeys = useCallback(async (token: string) => {
    try {
      setApiKeysLoading(true)
      const res = await fetch(`${API_BASE}/admin/api-keys`, { headers: { Authorization: `Bearer ${token}` } })
      if (res.status === 401) { handleSessionExpired(); return }
      if (res.ok) setApiKeys(await res.json())
    } finally {
      setApiKeysLoading(false)
    }
  }, [handleSessionExpired])
  const fetchUsdtCredit = useCallback(async (token: string) => {
    try {
      setUsdtLoading(true)
      const res = await fetch(`${API_BASE}/admin/usdt-credit`, { headers: { Authorization: `Bearer ${token}` } })
      if (res.status === 401) { handleSessionExpired(); return }
      if (res.ok) setUsdtRows(await res.json())
    } finally {
      setUsdtLoading(false)
    }
  }, [handleSessionExpired])
  const fetchWithdrawals = useCallback(async (token: string) => {
    try {
      setWithdrawalsLoading(true)
      const url = withdrawalFilter ? `${API_BASE}/admin/withdrawals?status=${withdrawalFilter}` : `${API_BASE}/admin/withdrawals`
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (res.status === 401) { handleSessionExpired(); return }
      if (res.ok) setWithdrawals(await res.json())
    } finally {
      setWithdrawalsLoading(false)
    }
  }, [withdrawalFilter, handleSessionExpired])
  const fetchReferrals = useCallback(async (token: string) => {
    try {
      setReferralsLoading(true)
      const res = await fetch(`${API_BASE}/admin/referrals`, { headers: { Authorization: `Bearer ${token}` } })
      if (res.status === 401) { handleSessionExpired(); return }
      if (res.ok) setReferrals(await res.json())
    } finally {
      setReferralsLoading(false)
    }
  }, [handleSessionExpired])
  const fetchNotifications = useCallback(async (token: string) => {
    try {
      setNotificationsLoading(true)
      const res = await fetch(`${API_BASE}/admin/notifications`, { headers: { Authorization: `Bearer ${token}` } })
      if (res.status === 401) { handleSessionExpired(); return }
      if (res.ok) setNotifications(await res.json())
    } finally {
      setNotificationsLoading(false)
    }
  }, [handleSessionExpired])
  const fetchAdminSettings = useCallback(async (token: string) => {
    try {
      setSettingsLoading(true)
      const res = await fetch(`${API_BASE}/admin/settings`, { headers: { Authorization: `Bearer ${token}` } })
      if (res.status === 401) { handleSessionExpired(); return }
      if (res.ok) setAdminSettings(await res.json())
    } finally {
      setSettingsLoading(false)
    }
  }, [handleSessionExpired])

  useEffect(() => {
    if (section === "apiKeys" && backendToken) void fetchApiKeys(backendToken)
  }, [section, backendToken, fetchApiKeys])
  useEffect(() => {
    if (section === "usdtCredit" && backendToken) void fetchUsdtCredit(backendToken)
  }, [section, backendToken, fetchUsdtCredit])
  useEffect(() => {
    if (section === "withdrawals" && backendToken) void fetchWithdrawals(backendToken)
  }, [section, backendToken, fetchWithdrawals])
  useEffect(() => {
    if (section === "referrals" && backendToken) void fetchReferrals(backendToken)
  }, [section, backendToken, fetchReferrals])
  useEffect(() => {
    if (section === "notifications" && backendToken) void fetchNotifications(backendToken)
  }, [section, backendToken, fetchNotifications])
  useEffect(() => {
    if (section === "settings" && backendToken) void fetchAdminSettings(backendToken)
  }, [section, backendToken, fetchAdminSettings])

  const retryFailure = async (failureId: string, userId: number | null) => {
    if (!backendToken) return
    setRetryError(null)
    setRetryingId(failureId)
    try {
      const res = await fetch(`${API_BASE}/admin/api-failures/retry`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${backendToken}`,
        },
        body: JSON.stringify(userId != null ? { user_id: userId } : { failure_id: failureId }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) {
        setFailures((prev) => prev.filter((f) => f.id !== failureId))
        void fetchFailures(backendToken)
      } else {
        setRetryError(typeof data.detail === "string" ? data.detail : "Retry failed")
      }
    } finally {
      setRetryingId(null)
    }
  }

  const handleUpdate = async (user: AdminUser, updates: Partial<AdminUser>) => {
    if (!backendToken) return
    const body: Record<string, unknown> = {
      plan_tier: updates.plan_tier,
      pro_expiry: updates.pro_expiry,
      rebalance_interval: updates.rebalance_interval,
    }
    if (updates.tokens_remaining !== undefined) body.tokens_remaining = updates.tokens_remaining
    const res = await fetch(`${API_BASE}/admin/users/${user.id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${backendToken}`,
      },
      body: JSON.stringify(body),
    })
    if (res.status === 401) { handleSessionExpired(); return }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      toast.error(typeof data.detail === "string" ? data.detail : "Update failed")
      return
    }
    const updated = await res.json()
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
    toast.success("User updated")
  }

  const adminBotStart = async (userId: number) => {
    if (!backendToken) return
    try {
      const res = await fetch(`${API_BASE}/admin/bot/start/${userId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${backendToken}` },
      })
      if (res.ok) void fetchUsers(backendToken)
    } catch {
      // ignore
    }
  }

  const adminBotRestart = async (userId: number) => {
    if (!backendToken) return
    try {
      await fetch(`${API_BASE}/admin/bot/stop/${userId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${backendToken}` },
      })
      await new Promise((r) => setTimeout(r, 2000))
      const res = await fetch(`${API_BASE}/admin/bot/start/${userId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${backendToken}` },
      })
      if (res.ok) void fetchUsers(backendToken)
    } catch {
      // ignore
    }
  }

  const adminBotStop = async (userId: number) => {
    if (!backendToken) return
    setStopCooldownUntil((prev) => ({ ...prev, [userId]: Date.now() + 4000 }))
    setTimeout(() => {
      setStopCooldownUntil((prev) => {
        const next = { ...prev }
        delete next[userId]
        return next
      })
    }, 4000)
    try {
      const res = await fetch(`${API_BASE}/admin/bot/stop/${userId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${backendToken}` },
      })
      if (res.ok) void fetchUsers(backendToken)
    } catch {
      // ignore
    }
  }

  const fetchBotLogs = async () => {
    const uid = parseInt(botLogsUserId, 10)
    if (!backendToken || isNaN(uid)) return
    setBotLogsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/admin/bot/logs/${uid}`, {
        headers: { Authorization: `Bearer ${backendToken}` },
      })
      const data = await res.json().catch(() => ({}))
      setBotLogs(Array.isArray(data.lines) ? data.lines : [])
    } catch {
      setBotLogs([])
    } finally {
      setBotLogsLoading(false)
    }
  }

  const triggerDeduction = async () => {
    if (!backendToken) return false
    setTriggerLoading(true)
    try {
      const res = await fetch(`${API_BASE}/admin/deduction/trigger`, {
        method: "POST",
        headers: { Authorization: `Bearer ${backendToken}` },
      })
      if (res.ok) {
        void fetchDeductionLogs(backendToken)
        return true
      }
      let message = "Deduction trigger failed"
      try {
        const errBody = await res.json()
        if (typeof errBody?.detail === "string") message = errBody.detail
      } catch {
        const text = await res.text()
        if (text) message = text.slice(0, 200)
      }
      toast.error(message)
      return false
    } finally {
      setTriggerLoading(false)
    }
  }

  const rollbackDeduction = async () => {
    const uid = parseInt(rollbackUserId, 10)
    if (!backendToken || isNaN(uid) || !rollbackDate) return false
    setRollbackLoading(true)
    try {
      const res = await fetch(
        `${API_BASE}/admin/deduction/rollback/${uid}/${rollbackDate}`,
        { method: "POST", headers: { Authorization: `Bearer ${backendToken}` } }
      )
      if (res.ok) {
        setRollbackUserId("")
        setRollbackDate("")
        void fetchUsers(backendToken)
        void fetchDeductionLogs(backendToken)
        return true
      }
      toast.error("Rollback failed")
      return false
    } finally {
      setRollbackLoading(false)
    }
  }

  const exportUsersCsvWithAuth = () => {
    if (!backendToken) return
    fetch(`${API_BASE}/admin/users/export`, { headers: { Authorization: `Bearer ${backendToken}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a")
        a.href = URL.createObjectURL(blob)
        a.download = "users_export.csv"
        a.click()
        URL.revokeObjectURL(a.href)
      })
      .catch(() => {})
  }

  const filteredUsers = users.filter(
    (u) =>
      !userSearch.trim() ||
      u.email.toLowerCase().includes(userSearch.toLowerCase()) ||
      (u.plan_tier || "").toLowerCase().includes(userSearch.toLowerCase()) ||
      (u.bot_status || "").toLowerCase().includes(userSearch.toLowerCase())
  )
  const botStatusOrder = (s: string | null | undefined) => {
    const x = (s ?? "").toLowerCase()
    if (x === "error" || x === "failed") return 0
    if (x === "running") return 1
    if (x === "starting") return 2
    return 3
  }
  const sortedUsers = [...filteredUsers].sort((a, b) => botStatusOrder(a.bot_status) - botStatusOrder(b.bot_status))
  const sortedUsersForBot = [...users].sort((a, b) => botStatusOrder(a.bot_status) - botStatusOrder(b.bot_status))

  if (sessionStatus === "loading" || (sessionStatus === "authenticated" && !backendToken)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    )
  }

  if (sessionStatus === "unauthenticated") {
    const locale = pathname?.startsWith("/zh") ? "zh" : "en"
    router.replace(`/${locale}/admin-login`)
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Redirecting to admin login…</p>
      </div>
    )
  }

  if (error && backendToken && !loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <p className="text-sm text-muted-foreground">{error}</p>
          </CardHeader>
          <CardContent>
            <Link href="/dashboard">
              <Button variant="outline" className="w-full">Go to dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row">
      <header className="md:hidden border-b border-border bg-card px-4 py-3 flex items-center justify-between">
        <span className="font-semibold text-foreground">Admin</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground truncate max-w-[120px]">{session?.user?.email}</span>
          <Button variant="ghost" size="sm" onClick={() => signOut({ callbackUrl: "/" })}>
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <aside className="w-full md:w-56 border-b md:border-b-0 md:border-r border-border bg-card p-3 flex md:flex-col gap-1">
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setSection(id)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm w-full text-left transition-colors ${
              section === id ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-secondary"
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </button>
        ))}
      </aside>

      <main className="flex-1 p-4 overflow-auto">
        <div className="hidden md:flex items-center justify-between mb-4">
          <h1 className="text-lg font-semibold text-foreground">Admin Panel</h1>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{session?.user?.email}</span>
            <Button variant="outline" size="sm" onClick={() => signOut({ callbackUrl: "/" })}>
              <LogOut className="h-4 w-4 mr-1" />
              Sign out
            </Button>
          </div>
        </div>

        {section === "users" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>User Management</CardTitle>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => backendToken && fetchUsers(backendToken)}>
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Refresh
                </Button>
                <Button size="sm" variant="outline" onClick={exportUsersCsvWithAuth}>
                  <Download className="h-4 w-4 mr-1" />
                  Export CSV
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <Input
                placeholder="Search by email, plan, bot status…"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                className="max-w-sm mb-4"
              />
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading users…</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-2">ID</th>
                        <th className="text-left py-2 px-2">Email</th>
                        <th className="text-left py-2 px-2">Plan</th>
                        <th className="text-left py-2 px-2">Tokens</th>
                        <th className="text-left py-2 px-2">Bot</th>
                        <th className="text-left py-2 px-2">Status</th>
                        <th className="text-left py-2 px-2">Created</th>
                        <th className="text-right py-2 px-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedUsers.map((u) => (
                        <tr key={u.id} className="border-b border-border/50">
                          <td className="py-2 px-2">{u.id}</td>
                          <td className="py-2 px-2 font-medium">
                            <Link href={`/admin/users/${u.id}`} className="text-primary hover:underline">{u.email}</Link>
                          </td>
                          <td className="py-2 px-2">{u.plan_tier}</td>
                          <td className="py-2 px-2">{u.tokens_remaining != null ? u.tokens_remaining.toFixed(0) : "—"}</td>
                          <td className="py-2 px-2"><BotStatusBadge status={u.bot_status} /></td>
                          <td className="py-2 px-2">{u.status}</td>
                          <td className="py-2 px-2 text-muted-foreground">{u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}</td>
                          <td className="py-2 px-2">
                            <div className="flex items-center justify-end gap-2">
                              <span className="text-muted-foreground text-xs">{u.plan_tier ?? "—"}</span>
                              <Link href={`/admin/users/${u.id}`}>
                                <Button size="sm" variant="ghost" className="h-7 text-xs">View</Button>
                              </Link>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {section === "users" && (
          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Bulk token adjustment</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-2">One line per user: user_id,amount (e.g. 5,100)</p>
              <textarea
                className="w-full rounded border border-border p-2 text-sm min-h-[80px]"
                placeholder="5,100&#10;7,50"
                value={bulkTokenInput}
                onChange={(e) => setBulkTokenInput(e.target.value)}
              />
              <Button
                className="mt-2"
                size="sm"
                onClick={async () => {
                  if (!backendToken) return
                  const lines = bulkTokenInput.trim().split(/\n/).filter(Boolean)
                  const items = lines.map((line) => {
                    const [a, b] = line.split(",").map((s) => s.trim())
                    return { user_id: parseInt(a, 10), amount: parseFloat(b || "0") }
                  }).filter((i) => !isNaN(i.user_id) && !isNaN(i.amount) && i.amount > 0)
                  if (items.length === 0) {
                    toast.error("Enter at least one valid line: user_id,amount")
                    return
                  }
                  if (!confirm(`Apply tokens to ${items.length} user(s)?`)) return
                  const res = await fetch(`${API_BASE}/admin/tokens/bulk-add`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Authorization: `Bearer ${backendToken}` },
                    body: JSON.stringify({ items }),
                  })
                  const data = await res.json().catch(() => ({}))
                  setBulkTokenResult(data.ok ? { success_count: data.success_count ?? 0, failed_count: data.failed_count ?? 0 } : null)
                  if (data.ok) {
                    toast.success(`Bulk tokens: ${data.success_count ?? 0} updated, ${data.failed_count ?? 0} failed`)
                    void fetchUsers(backendToken)
                  } else {
                    toast.error("Bulk token update failed")
                  }
                }}
              >
                Apply
              </Button>
              {bulkTokenResult && (
                <p className="text-sm text-muted-foreground mt-2">Success: {bulkTokenResult.success_count}, Failed: {bulkTokenResult.failed_count}</p>
              )}
            </CardContent>
          </Card>
        )}

        {section === "apiKeys" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>API Keys</CardTitle>
              <Button size="sm" variant="outline" onClick={() => backendToken && fetchApiKeys(backendToken)}>
                <RefreshCw className="h-4 w-4 mr-1" /> Refresh
              </Button>
            </CardHeader>
            <CardContent>
              {apiKeysLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-2">User ID</th>
                        <th className="text-left py-2 px-2">Email</th>
                        <th className="text-left py-2 px-2">Status</th>
                        <th className="text-left py-2 px-2">Key (masked)</th>
                        <th className="text-left py-2 px-2">Last tested</th>
                        <th className="text-left py-2 px-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {apiKeys.map((row) => (
                        <tr key={row.user_id} className="border-b border-border/50">
                          <td className="py-2 px-2">{row.user_id}</td>
                          <td className="py-2 px-2">{row.email}</td>
                          <td className="py-2 px-2">{row.has_keys ? "Set" : "Not set"}</td>
                          <td className="py-2 px-2 font-mono text-xs">{row.key_masked ?? "—"}</td>
                          <td className="py-2 px-2 text-muted-foreground">{row.last_tested_at ? new Date(row.last_tested_at).toLocaleString() : "—"}</td>
                          <td className="py-2 px-2">
                            {row.has_keys && (
                              <Button
                                size="sm"
                                variant="destructive"
                                className="h-7 text-xs"
                                onClick={async () => {
                                  if (!backendToken || !confirm("Reset API keys for this user? They will need to reconnect.")) return
                                  const res = await fetch(`${API_BASE}/admin/api-keys/${row.user_id}/reset`, { method: "POST", headers: { Authorization: `Bearer ${backendToken}` } })
                                  if (res.ok) { toast.success("API keys reset"); void fetchApiKeys(backendToken) } else toast.error("Reset failed")
                                }}
                              >
                                Reset
                              </Button>
                            )}
                            <Link href={`/admin/users/${row.user_id}`}>
                              <Button size="sm" variant="ghost" className="h-7 text-xs ml-1">View</Button>
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {section === "bot" && (
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle>Start / Stop bot by user</CardTitle>
                <Button size="sm" variant="outline" onClick={async () => { if (!backendToken) return; const res = await fetch(`${API_BASE}/admin/arq/restart`, { method: "POST", headers: { Authorization: `Bearer ${backendToken}` } }); if (res.ok) toast.success("ARQ restart signal sent (worker must be restarted externally)"); else toast.error("Request failed") }}>
                  Restart ARQ Worker
                </Button>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <p className="text-sm text-muted-foreground">Loading…</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left py-2 px-2">ID</th>
                          <th className="text-left py-2 px-2">Email</th>
                          <th className="text-left py-2 px-2">Bot</th>
                          <th className="text-left py-2 px-2">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedUsersForBot.map((u) => (
                          <tr key={u.id} className="border-b border-border/50">
                            <td className="py-2 px-2">{u.id}</td>
                            <td className="py-2 px-2">{u.email}</td>
                            <td className="py-2 px-2"><BotStatusBadge status={u.bot_status} /></td>
                            <td className="py-2 px-2 flex gap-1">
                              {((u.bot_status ?? "").toLowerCase() === "stopped" ? (
                                <Button size="sm" variant="outline" onClick={() => adminBotStart(u.id)}>
                                  <Play className="h-3 w-3 mr-1" />
                                  Start
                                </Button>
                              ) : (
                                <Button size="sm" variant="outline" onClick={() => adminBotRestart(u.id)}>
                                  <RefreshCw className="h-3 w-3 mr-1" />
                                  Restart
                                </Button>
                              ))}
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={(stopCooldownUntil[u.id] ?? 0) > Date.now()}
                                onClick={() => adminBotStop(u.id)}
                              >
                                <Square className="h-3 w-3 mr-1" />
                                {(stopCooldownUntil[u.id] ?? 0) > Date.now() ? "Stop (cooldown)" : "Stop"}
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Bot logs (terminal)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex gap-2 mb-3">
                  <Input
                    type="number"
                    placeholder="User ID"
                    value={botLogsUserId}
                    onChange={(e) => setBotLogsUserId(e.target.value)}
                    className="w-28"
                  />
                  <Button size="sm" onClick={fetchBotLogs} disabled={botLogsLoading}>
                    <FileCode className="h-4 w-4 mr-1" />
                    Load logs
                  </Button>
                </div>
                <pre className="bg-muted/50 rounded-lg p-3 text-xs overflow-auto max-h-80 whitespace-pre-wrap">
                  {botLogsLoading ? "Loading…" : botLogs.length ? botLogs.join("\n") : "Enter user ID and click Load logs."}
                </pre>
              </CardContent>
            </Card>
          </div>
        )}

        {section === "deduction" && (
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle>Token deduction</CardTitle>
                <Button size="sm" onClick={async () => { if (!confirm("Run daily token deduction now?")) return; const ok = await triggerDeduction(); if (ok) toast.success("Deduction run completed") }} disabled={triggerLoading}>
                  {triggerLoading ? "Running…" : "Manual trigger"}
                </Button>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-3">Run daily token deduction now. Logs below.</p>
                <div className="flex flex-wrap gap-2 mb-3">
                  <span className="text-xs text-muted-foreground self-center">Filter by date:</span>
                  <Input type="date" placeholder="From" className="w-40" value={deductionStartDate} onChange={(e) => setDeductionStartDate(e.target.value)} />
                  <Input type="date" placeholder="To" className="w-40" value={deductionEndDate} onChange={(e) => setDeductionEndDate(e.target.value)} />
                  <Button size="sm" variant="outline" onClick={() => backendToken && fetchDeductionLogs(backendToken)}>Apply filter</Button>
                </div>
                <div className="flex flex-wrap gap-2 mb-4">
                  <Input
                    placeholder="User ID"
                    value={rollbackUserId}
                    onChange={(e) => setRollbackUserId(e.target.value)}
                    className="w-28"
                  />
                  <Input
                    placeholder="Date YYYY-MM-DD"
                    value={rollbackDate}
                    onChange={(e) => setRollbackDate(e.target.value)}
                    className="w-36"
                  />
                  <Button size="sm" variant="outline" onClick={async () => { if (!confirm(`Rollback deduction for user ${rollbackUserId} on ${rollbackDate}? Tokens will be added back.`)) return; const ok = await rollbackDeduction(); if (ok) toast.success("Rollback completed") }} disabled={rollbackLoading}>
                    {rollbackLoading ? "…" : "Rollback"}
                  </Button>
                </div>
                {deductionLoading ? (
                  <p className="text-sm text-muted-foreground">Loading logs…</p>
                ) : (
                  <div className="overflow-x-auto max-h-96">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left py-2 px-2">User ID</th>
                          <th className="text-left py-2 px-2">Time</th>
                          <th className="text-left py-2 px-2">Deducted</th>
                          <th className="text-left py-2 px-2">After</th>
                        </tr>
                      </thead>
                      <tbody>
                        {deductionLogs.map((e, i) => (
                          <tr key={i} className="border-b border-border/50">
                            <td className="py-2 px-2">{e.user_id}</td>
                            <td className="py-2 px-2">{e.timestamp}</td>
                            <td className="py-2 px-2">{e.tokens_deducted}</td>
                            <td className="py-2 px-2">{e.tokens_remaining_after}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {deductionLogs.length === 0 && <p className="text-sm text-muted-foreground py-4">No deduction logs yet.</p>}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {section === "usdtCredit" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>USDT Credit</CardTitle>
              <Button size="sm" variant="outline" onClick={() => backendToken && fetchUsdtCredit(backendToken)}>
                <RefreshCw className="h-4 w-4 mr-1" /> Refresh
              </Button>
            </CardHeader>
            <CardContent>
              {usdtLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-2">User ID</th>
                        <th className="text-left py-2 px-2">Email</th>
                        <th className="text-left py-2 px-2">Balance</th>
                        <th className="text-left py-2 px-2">Locked (Pending)</th>
                        <th className="text-left py-2 px-2">Earned</th>
                        <th className="text-left py-2 px-2">Withdrawn</th>
                        <th className="text-left py-2 px-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usdtRows.map((r) => (
                        <tr key={r.user_id} className="border-b border-border/50">
                          <td className="py-2 px-2">{r.user_id}</td>
                          <td className="py-2 px-2">{r.email}</td>
                          <td className="py-2 px-2">{r.usdt_credit}</td>
                          <td className="py-2 px-2 text-amber-600">{(r.locked_pending ?? 0).toFixed(2)}</td>
                          <td className="py-2 px-2">{r.total_earned}</td>
                          <td className="py-2 px-2">{r.total_withdrawn}</td>
                          <td className="py-2 px-2">
                            <Link href={`/admin/users/${r.user_id}`}>
                              <Button size="sm" variant="outline" className="h-7 text-xs">View / Adjust</Button>
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {section === "withdrawals" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>Withdrawals</CardTitle>
              <div className="flex gap-2">
                <select
                  className="rounded border border-border px-2 py-1 text-sm"
                  value={withdrawalFilter}
                  onChange={(e) => setWithdrawalFilter(e.target.value)}
                >
                  <option value="">All</option>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
                <Button size="sm" variant="outline" onClick={() => backendToken && fetchWithdrawals(backendToken)}>
                  <RefreshCw className="h-4 w-4 mr-1" /> Refresh
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {withdrawalsLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-2">ID</th>
                        <th className="text-left py-2 px-2">User</th>
                        <th className="text-left py-2 px-2">Amount</th>
                        <th className="text-left py-2 px-2">Address</th>
                        <th className="text-left py-2 px-2">Status</th>
                        <th className="text-left py-2 px-2">Created</th>
                        <th className="text-left py-2 px-2">Processed By</th>
                        <th className="text-left py-2 px-2">Note</th>
                        <th className="text-left py-2 px-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {withdrawals.map((w) => (
                        <tr key={w.id} className={`border-b border-border/50 ${w.status === "pending" ? "bg-amber-500/10" : ""}`}>
                          <td className="py-2 px-2">{w.id}</td>
                          <td className="py-2 px-2">{w.email} ({w.user_id})</td>
                          <td className="py-2 px-2">
                            <button
                              type="button"
                              onClick={() => { navigator.clipboard.writeText(String(w.amount)); toast.success("Amount copied") }}
                              className="inline-flex items-center gap-1.5 rounded hover:bg-muted/80 px-1 -mx-1 py-0.5"
                              title="Copy amount"
                            >
                              {w.amount}
                              <Copy className="h-3 w-3 shrink-0 text-muted-foreground" />
                            </button>
                          </td>
                          <td className="py-2 px-2 max-w-[180px]">
                            <button
                              type="button"
                              onClick={() => { navigator.clipboard.writeText(w.address); toast.success("Address copied") }}
                              className="inline-flex items-center gap-1.5 rounded hover:bg-muted/80 px-1 -mx-1 py-0.5 w-full text-left truncate"
                              title={w.address}
                            >
                              <span className="truncate">{w.address}</span>
                              <Copy className="h-3 w-3 shrink-0 text-muted-foreground" />
                            </button>
                          </td>
                          <td className="py-2 px-2">{w.status}</td>
                          <td className="py-2 px-2 text-muted-foreground">{w.created_at ? new Date(w.created_at).toLocaleString() : "—"}</td>
                          <td className="py-2 px-2 text-muted-foreground text-xs">{w.processed_by ?? "—"}</td>
                          <td className="py-2 px-2 text-muted-foreground text-xs max-w-[140px] truncate" title={w.rejection_note ?? undefined}>{w.rejection_note ?? "—"}</td>
                          <td className="py-2 px-2 flex gap-1">
                            {w.status === "pending" && (
                              <>
                                <Button size="sm" className="h-7 text-xs bg-primary" onClick={async () => { if (!backendToken || !confirm(`Approve withdrawal #${w.id} (${w.amount} USDT Credit for ${w.email})?`)) return; const res = await fetch(`${API_BASE}/admin/withdrawals/${w.id}/approve`, { method: "POST", headers: { Authorization: `Bearer ${backendToken}` } }); if (res.ok) { toast.success("Withdrawal approved"); void fetchWithdrawals(backendToken) } else toast.error("Approve failed") }}>Approve</Button>
                                <Button size="sm" variant="destructive" className="h-7 text-xs" onClick={() => { setRejectModalWid(w.id); setRejectNote("") }}>Reject</Button>
                              </>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {rejectModalWid != null && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setRejectModalWid(null)}>
            <div className="rounded-xl border border-border bg-card p-5 max-w-md w-full shadow-xl" onClick={(e) => e.stopPropagation()}>
              <p className="text-sm font-medium mb-2">Reject withdrawal #{rejectModalWid}</p>
              <p className="text-xs text-muted-foreground mb-2">Reason for rejection (optional, visible to user):</p>
              <textarea className="w-full rounded border border-border px-3 py-2 text-sm mb-3 min-h-[80px]" placeholder="e.g. Invalid address" value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} />
              <div className="flex gap-2 justify-end">
                <Button variant="outline" size="sm" onClick={() => setRejectModalWid(null)}>Cancel</Button>
                <Button variant="destructive" size="sm" onClick={async () => {
                  if (!backendToken) return
                  const res = await fetch(`${API_BASE}/admin/withdrawals/${rejectModalWid}/reject`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${backendToken}` }, body: JSON.stringify({ rejection_note: rejectNote.trim() || undefined }) })
                  if (res.ok) { toast.success("Withdrawal rejected"); setRejectModalWid(null); void fetchWithdrawals(backendToken) } else toast.error("Reject failed")
                }}>Reject</Button>
              </div>
            </div>
          </div>
        )}

        {section === "referrals" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>Referrals</CardTitle>
              <Button size="sm" variant="outline" onClick={() => backendToken && fetchReferrals(backendToken)}>
                <RefreshCw className="h-4 w-4 mr-1" /> Refresh
              </Button>
            </CardHeader>
            <CardContent>
              {referralsLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-2">User ID</th>
                        <th className="text-left py-2 px-2">Email</th>
                        <th className="text-left py-2 px-2">Referral Code</th>
                        <th className="text-left py-2 px-2">Referrer</th>
                        <th className="text-left py-2 px-2">Downlines</th>
                        <th className="text-left py-2 px-2">Earnings</th>
                        <th className="text-left py-2 px-2">Tree</th>
                      </tr>
                    </thead>
                    <tbody>
                      {referrals.map((r) => (
                        <tr key={r.user_id} className="border-b border-border/50">
                          <td className="py-2 px-2">{r.user_id}</td>
                          <td className="py-2 px-2">{r.email}</td>
                          <td className="py-2 px-2 font-mono text-xs">{r.referral_code ?? "—"}</td>
                          <td className="py-2 px-2">{r.referrer_email ?? "—"} {r.referrer_id != null && `(${r.referrer_id})`}</td>
                          <td className="py-2 px-2">{r.downline_count}</td>
                          <td className="py-2 px-2">{r.referral_earnings}</td>
                          <td className="py-2 px-2">
                            <Link href={`/admin/users/${r.user_id}`}>
                              <Button size="sm" variant="ghost" className="h-7 text-xs">View tree</Button>
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {section === "notifications" && (
          <Card>
            <CardHeader>
              <CardTitle>Send notification</CardTitle>
            </CardHeader>
            <CardContent>
              <NotificationFormInline backendToken={backendToken} onSent={() => backendToken && fetchNotifications(backendToken)} />
            </CardContent>
            <CardHeader>
              <CardTitle>Sent notifications</CardTitle>
            </CardHeader>
            <CardContent>
              {notificationsLoading ? <p className="text-sm text-muted-foreground">Loading…</p> : (
                <ul className="space-y-2 max-h-64 overflow-y-auto">
                  {notifications.map((n) => (
                    <li key={n.id} className="rounded border border-border p-2 text-sm">
                      <span className="font-medium">{n.title}</span> — {n.type} {n.target_user_id != null ? `(user ${n.target_user_id})` : "(all)"} — {n.created_at ? new Date(n.created_at).toLocaleString() : ""}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )}

        {section === "settings" && (
          <Card>
            <CardHeader>
              <CardTitle>Admin settings</CardTitle>
            </CardHeader>
            <CardContent>
              <AdminSettingsFormInline settings={adminSettings} loading={settingsLoading} backendToken={backendToken} onSave={() => backendToken && fetchAdminSettings(backendToken)} />
            </CardContent>
          </Card>
        )}

        {section === "health" && (
          <Card>
            <CardHeader>
              <CardTitle>System health</CardTitle>
            </CardHeader>
            <CardContent>
              {healthLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : health ? (
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-lg border border-border p-4">
                    <p className="text-sm font-medium text-foreground">Redis</p>
                    <p className={`text-sm ${health.redis === "ok" ? "text-chart-1" : "text-destructive"}`}>{health.redis}</p>
                  </div>
                  <div className="rounded-lg border border-border p-4">
                    <p className="text-sm font-medium text-foreground">Database</p>
                    <p className={`text-sm ${health.db === "ok" ? "text-chart-1" : "text-destructive"}`}>{health.db}</p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Could not load health.</p>
              )}
            </CardContent>
          </Card>
        )}

        {section === "audit" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>Audit logs</CardTitle>
              <div className="flex gap-2 flex-wrap">
                <Input placeholder="Action filter" className="w-32" value={auditFilterAction} onChange={(e) => setAuditFilterAction(e.target.value)} />
                <Input placeholder="Email filter" className="w-40" value={auditFilterEmail} onChange={(e) => setAuditFilterEmail(e.target.value)} />
                <Button size="sm" variant="outline" onClick={() => backendToken && fetchAuditLogs(backendToken)}>
                  <RefreshCw className="h-4 w-4 mr-1" /> Refresh
                </Button>
                <Button size="sm" variant="outline" onClick={async () => { if (!backendToken) return; const params = new URLSearchParams(); if (auditFilterAction) params.set("action", auditFilterAction); if (auditFilterEmail) params.set("email", auditFilterEmail); const r = await fetch(`${API_BASE}/admin/audit-logs/export?${params}`, { headers: { Authorization: `Bearer ${backendToken}` } }); const blob = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "audit_logs.csv"; a.click(); URL.revokeObjectURL(a.href); }}>
                  <Download className="h-4 w-4 mr-1" /> Export CSV
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {auditLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <div className="overflow-x-auto max-h-96">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-2">Time</th>
                        <th className="text-left py-2 px-2">Email</th>
                        <th className="text-left py-2 px-2">Action</th>
                        <th className="text-left py-2 px-2">Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLogs.map((e, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="py-2 px-2 text-muted-foreground">{e.ts}</td>
                          <td className="py-2 px-2">{e.email}</td>
                          <td className="py-2 px-2 font-medium">{e.action}</td>
                          <td className="py-2 px-2">{JSON.stringify(e.detail)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {auditLogs.length === 0 && !auditLoading && <p className="text-sm text-muted-foreground py-4">No audit entries yet.</p>}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {section === "failures" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>API Failures</CardTitle>
              <Button size="sm" variant="outline" onClick={() => backendToken && fetchFailures(backendToken)}>
                <RefreshCw className="h-4 w-4 mr-1" />
                Refresh
              </Button>
            </CardHeader>
            <CardContent>
              {retryError && <p className="text-sm text-destructive mb-2">{retryError}</p>}
              {failuresLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {failures.length === 0 && !failuresLoading && <p className="text-sm text-muted-foreground">No recent failures.</p>}
                  {failures.map((f) => (
                    <div key={f.id} className="rounded border border-amber-500/30 bg-amber-500/5 p-2 text-sm">
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">{new Date(f.ts).toLocaleString()}</span>
                        {f.user_id != null && (
                          <Button
                            size="sm"
                            variant="secondary"
                            className="h-6 text-xs"
                            disabled={retryingId === f.id}
                            onClick={() => retryFailure(f.id, f.user_id)}
                          >
                            {retryingId === f.id ? "…" : "Retry"}
                          </Button>
                        )}
                      </div>
                      <p className="font-medium">{f.context}{f.user_id != null ? ` · user ${f.user_id}` : ""}</p>
                      <p className="text-muted-foreground truncate" title={f.error}>{f.error}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  )
}
