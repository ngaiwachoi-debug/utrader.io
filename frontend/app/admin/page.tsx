"use client"

import { useEffect, useState, useCallback } from "react"
import DashboardPage from "@/app/[locale]/dashboard/page"
import { AlertCircle, RefreshCw } from "lucide-react"

type AdminUser = {
  id: number
  email: string
  plan_tier: string
  lending_limit: number
  rebalance_interval: number
  pro_expiry: string | null
  status: string
}

type ApiFailure = {
  id: string
  ts: string
  context: string
  user_id: number | null
  error: string
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

export default function AdminPage() {
  const [idToken, setIdToken] = useState<string | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [failures, setFailures] = useState<ApiFailure[]>([])
  const [failuresLoading, setFailuresLoading] = useState(false)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [retryError, setRetryError] = useState<string | null>(null)

  const fetchUsers = async (token: string) => {
    try {
      setLoading(true)
      setError(null)
      const res = await fetch(`${API_BASE}/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        throw new Error("Not authorized")
      }
      const data = await res.json()
      setUsers(data)
    } catch (e) {
      console.error(e)
      setError("Admin access requires logging in with ngaiwachoi@gmail.com.")
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleToken = () => {
    const token = prompt("Paste your Google ID token for ngaiwachoi@gmail.com:")
    if (!token) return
    setIdToken(token)
    void fetchUsers(token)
  }

  const fetchFailures = useCallback(
    async (token: string) => {
      try {
        setFailuresLoading(true)
        const res = await fetch(`${API_BASE}/admin/api-failures?limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        const data = await res.json()
        setFailures(Array.isArray(data) ? data : [])
      } catch {
        // ignore
      } finally {
        setFailuresLoading(false)
      }
    },
    []
  )

  useEffect(() => {
    if (!idToken) return
    void fetchFailures(idToken)
    const interval = setInterval(() => fetchFailures(idToken), 30_000)
    return () => clearInterval(interval)
  }, [idToken, fetchFailures])

  const retryFailure = async (failureId: string, userId: number | null) => {
    if (!idToken) return
    setRetryError(null)
    setRetryingId(failureId)
    try {
      const res = await fetch(`${API_BASE}/admin/api-failures/retry`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${idToken}`,
        },
        body: JSON.stringify(userId != null ? { user_id: userId } : { failure_id: failureId }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) {
        setFailures((prev) => prev.filter((f) => f.id !== failureId))
        void fetchFailures(idToken)
      } else {
        setRetryError(typeof data.detail === "string" ? data.detail : "Retry failed")
      }
    } finally {
      setRetryingId(null)
    }
  }

  const handleUpdate = async (user: AdminUser, updates: Partial<AdminUser>) => {
    if (!idToken) return
    const res = await fetch(`${API_BASE}/admin/users/${user.id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${idToken}`,
      },
      body: JSON.stringify({
        plan_tier: updates.plan_tier,
        pro_expiry: updates.pro_expiry,
        lending_limit: updates.lending_limit,
        rebalance_interval: updates.rebalance_interval,
      }),
    })
    if (!res.ok) return
    const updated = await res.json()
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
  }

  if (!idToken) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-lg">
          <h1 className="text-lg font-semibold text-foreground mb-2">Admin Login</h1>
          <p className="text-xs text-muted-foreground mb-4">
            Admin access is restricted to <span className="font-semibold">ngaiwachoi@gmail.com</span>.
            Generate a Google ID token for this account and paste it below.
          </p>
          <button
            onClick={handleGoogleToken}
            className="w-full rounded-lg bg-emerald px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-emerald-dark transition-colors"
          >
            Paste Google ID Token
          </button>
          {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex">
      <div className="flex-1">
        <DashboardPage />
      </div>
      <aside className="hidden lg:block w-[360px] border-l border-border bg-card p-4 overflow-y-auto">
        <h2 className="text-sm font-semibold text-foreground mb-3">Admin Panel</h2>
        {loading && <p className="text-xs text-muted-foreground mb-2">Loading users…</p>}
        {error && <p className="text-xs text-destructive mb-2">{error}</p>}
        <button
          onClick={() => idToken && fetchUsers(idToken)}
          className="mb-3 rounded-lg bg-secondary px-3 py-1.5 text-xs text-foreground hover:border-emerald/50 border border-border transition-colors"
        >
          Refresh Users
        </button>

        <h3 className="text-xs font-semibold text-foreground mt-4 mb-2 flex items-center gap-1.5">
          <AlertCircle className="h-3.5 w-3.5" />
          API Failures
        </h3>
        {failuresLoading && <p className="text-[11px] text-muted-foreground mb-1">Loading…</p>}
        <button
          type="button"
          onClick={() => idToken && fetchFailures(idToken)}
          className="mb-2 flex items-center gap-1 rounded bg-secondary px-2 py-1 text-[10px] text-foreground hover:bg-secondary/80"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </button>
        {retryError && (
          <p className="mb-2 text-[11px] text-red-500">{retryError}</p>
        )}
        <div className="space-y-2 max-h-48 overflow-y-auto">
          {failures.length === 0 && !failuresLoading && (
            <p className="text-[11px] text-muted-foreground">No recent failures.</p>
          )}
          {failures.map((f) => (
            <div
              key={f.id}
              className="rounded border border-amber-500/30 bg-amber-500/5 p-2 text-[11px]"
            >
              <div className="flex items-start justify-between gap-1">
                <span className="text-muted-foreground shrink-0">
                  {new Date(f.ts).toLocaleString()}
                </span>
                {f.user_id != null && (
                  <button
                    type="button"
                    disabled={retryingId === f.id}
                    onClick={() => retryFailure(f.id, f.user_id)}
                    className="shrink-0 rounded bg-amber-600 px-1.5 py-0.5 text-[10px] font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                  >
                    {retryingId === f.id ? "…" : "Retry"}
                  </button>
                )}
              </div>
              <p className="mt-0.5 font-medium text-foreground">
                {f.context}
                {f.user_id != null && ` · user ${f.user_id}`}
              </p>
              <p className="mt-0.5 truncate text-muted-foreground" title={f.error}>
                {f.error}
              </p>
            </div>
          ))}
        </div>

        <div className="space-y-3 mt-4">
          {users.map((u) => (
            <div key={u.id} className="rounded-lg border border-border bg-background/60 p-3 text-xs">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-foreground">{u.email}</span>
                <span className="rounded-full bg-emerald/10 px-2 py-0.5 text-[10px] font-semibold text-emerald">
                  {u.plan_tier.toUpperCase()}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground mb-1">
                Limit: ${u.lending_limit.toLocaleString()} · Every {u.rebalance_interval}m
              </p>
              <p className="text-[11px] text-muted-foreground mb-2">
                Expiry: {u.pro_expiry ? new Date(u.pro_expiry).toLocaleString() : "—"} · Status: {u.status}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {["trial", "pro", "expert", "guru"].map((tier) => (
                  <button
                    key={tier}
                    onClick={() => handleUpdate(u, { plan_tier: tier })}
                    className={`rounded-full px-2 py-0.5 text-[10px] border ${
                      u.plan_tier === tier
                        ? "bg-emerald text-primary-foreground border-emerald"
                        : "bg-card text-muted-foreground border-border"
                    }`}
                  >
                    {tier}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  )
}

