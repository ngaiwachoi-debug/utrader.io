"use client"

import { useEffect, useState, useCallback } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useSession, signOut } from "next-auth/react"
import { getBackendToken } from "@/lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ArrowLeft } from "lucide-react"

import { API_BASE } from "@/lib/api-config"

type Overview = {
  user: Record<string, unknown>
  token_balance?: Record<string, unknown>
  usdt_credit?: Record<string, unknown>
  profit_snapshot?: Record<string, unknown>
  referral?: Record<string, unknown>
  api_key_status?: Record<string, unknown>
  withdrawals: Record<string, unknown>[]
  deduction_history: Record<string, unknown>[]
  token_add_history?: { amount: number; reason: string; created_at: string; detail?: string | null }[]
  audit_entries: Record<string, unknown>[]
  edits_locked?: boolean
}

export default function AdminUserDetailPage() {
  const params = useParams()
  const user_id = typeof params?.user_id === "string" ? params.user_id : ""
  const { data: session, status } = useSession()
  const [token, setToken] = useState<string | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addTokensAmount, setAddTokensAmount] = useState("")
  const [deductTokensAmount, setDeductTokensAmount] = useState("")
  const [tokenMessage, setTokenMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [tokenLoading, setTokenLoading] = useState<"add" | "deduct" | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [profileMessage, setProfileMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [usdtMessage, setUsdtMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [apiKeyMessage, setApiKeyMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [adjustUsdt, setAdjustUsdt] = useState("")
  const [setPlanTier, setSetPlanTier] = useState("")
  const [extendDays, setExtendDays] = useState("")

  useEffect(() => {
    if (status !== "authenticated") return
    getBackendToken().then((t) => setToken(t ?? null))
  }, [status])

  const handleSessionExpired = useCallback(() => {
    signOut({ callbackUrl: "/" })
    window.location.href = "/"
  }, [signOut])

  useEffect(() => {
    if (!token || !user_id) return
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => {
        if (r.status === 401) { handleSessionExpired(); return null }
        if (!r.ok) throw new Error("Not found")
        return r.json()
      })
      .then((data) => { if (data != null) setOverview(data) })
      .catch(() => setError("Failed to load"))
      .finally(() => setLoading(false))
  }, [token, user_id, handleSessionExpired])

  if (status === "loading" || !token) {
    return <div className="min-h-screen flex items-center justify-center bg-background"><p className="text-sm text-muted-foreground">Loading…</p></div>
  }
  if (status === "unauthenticated") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Link href="/login"><Button>Sign in</Button></Link>
      </div>
    )
  }
  if (error || (!loading && !overview)) {
    return (
      <div className="min-h-screen p-4">
        <Link href="/admin" className="text-sm text-chart-1 hover:underline flex items-center gap-1 mb-4"><ArrowLeft className="h-4 w-4" /> Back to Admin</Link>
        <p className="text-destructive">{error || "User not found."}</p>
      </div>
    )
  }
  if (loading || !overview) {
    return <div className="min-h-screen flex items-center justify-center bg-background"><p className="text-sm text-muted-foreground">Loading user…</p></div>
  }

  const u = overview.user as Record<string, unknown>
  const uid = Number(user_id)
  const editsDisabled = actionLoading !== null || tokenLoading !== null || !!overview?.edits_locked
  const refetchOverview = async () => {
    if (!token) return
    const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } })
    if (r.ok) setOverview(await r.json())
  }

  return (
    <div className="min-h-screen bg-background p-4">
      <Link href="/admin" className="text-sm text-chart-1 hover:underline flex items-center gap-1 mb-4">
        <ArrowLeft className="h-4 w-4" /> Back to Admin
      </Link>

      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <h1 className="text-xl font-semibold text-foreground">
          User: {String(u.email)} (ID {user_id})
        </h1>
      </div>

      {overview?.edits_locked && (
        <p className="mb-4 rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-2 text-sm text-amber-700 dark:text-amber-400">
          Edits are disabled during the daily fee window (09:55–10:35 UTC). Buttons will be clickable again after the job finishes.
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-1">
            <p>Plan: {String(u.plan_tier)} · Status: {String(u.status)} · Bot: {String(u.bot_status)}</p>
            <p>Pro expiry: {u.pro_expiry ? new Date(String(u.pro_expiry)).toLocaleString() : "—"}</p>
            <p>Created: {u.created_at ? new Date(String(u.created_at)).toLocaleString() : "—"}</p>
            <p>Referral code: {String(u.referral_code ?? "—")} · Referred by: {u.referred_by != null ? String(u.referred_by) : "—"}</p>
            {profileMessage && (
              <p className={`mt-2 text-xs break-words whitespace-pre-wrap max-w-2xl ${profileMessage.type === "success" ? "text-chart-1" : "text-destructive"}`}>{profileMessage.text}</p>
            )}
            <div className="flex flex-col gap-3 mt-2">
              <div className="flex flex-wrap items-center gap-2">
                <select className="rounded border border-border px-2 py-1 text-sm focus:text-black [&_option]:text-black" value={setPlanTier} onChange={(e) => { setSetPlanTier(e.target.value); setProfileMessage(null) }} disabled={editsDisabled}>
                  <option value="">Set plan…</option>
                  <option value="trial">trial</option>
                  <option value="free">free</option>
                  <option value="pro">pro</option>
                  <option value="ai_ultra">ai_ultra</option>
                  <option value="whales">whales</option>
                </select>
                <Button size="sm" type="button" disabled={editsDisabled || !setPlanTier || !token} onClick={async () => {
                  if (!token || !setPlanTier) return
                  setActionLoading("set_plan"); setProfileMessage(null)
                  try {
                    const res = await fetch(`${API_BASE}/admin/users/${uid}/set-plan`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ plan_tier: setPlanTier }) })
                    const data = await res.json().catch(() => ({}))
                    if (!res.ok) { setProfileMessage({ type: "error", text: `Set plan failed: ${res.status}. ${typeof data?.detail === "string" ? data.detail : data?.detail ?? "No details"}` }); return }
                    setSetPlanTier(""); setProfileMessage({ type: "success", text: `Plan set to ${setPlanTier}.` }); await refetchOverview()
                  } finally { setActionLoading(null) }
                }}>{actionLoading === "set_plan" ? "Saving…" : "Set plan"}</Button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Input type="number" placeholder="Extend expiry (days)" className="w-36" value={extendDays} onChange={(e) => { setExtendDays(e.target.value); setProfileMessage(null) }} disabled={editsDisabled} />
                <Button size="sm" type="button" disabled={editsDisabled || !extendDays || !token} onClick={async () => {
                  if (!token || extendDays === "") return
                  const days = parseInt(extendDays, 10); if (isNaN(days)) return
                  setActionLoading("extend_expiry"); setProfileMessage(null)
                  try {
                    const res = await fetch(`${API_BASE}/admin/users/${uid}/extend-expiry`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ days }) })
                    const data = await res.json().catch(() => ({}))
                    if (!res.ok) { setProfileMessage({ type: "error", text: `Extend expiry failed: ${res.status}. ${typeof data?.detail === "string" ? data.detail : data?.detail ?? "No details"}` }); return }
                    setExtendDays(""); setProfileMessage({ type: "success", text: `Expiry extended by ${days} days.` }); await refetchOverview()
                  } finally { setActionLoading(null) }
                }}>{actionLoading === "extend_expiry" ? "Saving…" : "Extend expiry"}</Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Token balance</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {overview.token_balance ? (
              <p>Remaining: {String(overview.token_balance.tokens_remaining)} · Total added: {String(overview.token_balance.total_tokens_added)} · Total deducted: {String(overview.token_balance.total_tokens_deducted)} · Last gross used: {String(overview.token_balance.last_gross_usd_used)}</p>
            ) : (
              <p>No balance row.</p>
            )}
            {((overview.token_add_history) ?? []).length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-medium text-muted-foreground mb-1">Token add history (recent)</p>
                <div className="overflow-x-auto max-h-48 border border-border rounded-md">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border bg-muted/50">
                        <th className="text-left py-1.5 px-2">Time</th>
                        <th className="text-left py-1.5 px-2">Amount</th>
                        <th className="text-left py-1.5 px-2">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(overview.token_add_history ?? []).slice(0, 20).map((e, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="py-1.5 px-2">{e.created_at}</td>
                          <td className="py-1.5 px-2">{e.amount}</td>
                          <td className="py-1.5 px-2">{e.detail ?? e.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {tokenMessage && (
              <p className={`mt-2 text-xs break-words whitespace-pre-wrap max-w-2xl ${tokenMessage.type === "success" ? "text-chart-1" : "text-destructive"}`}>{tokenMessage.text}</p>
            )}
            <div className="flex flex-wrap gap-4 mt-3">
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  placeholder="Amount to add"
                  className="w-28"
                  min={0}
                  step={1}
                  value={addTokensAmount}
                  onChange={(e) => { setAddTokensAmount(e.target.value); setTokenMessage(null) }}
                  disabled={editsDisabled}
                />
                <Button
                  type="button"
                  size="sm"
                  disabled={editsDisabled || !addTokensAmount.trim() || parseFloat(addTokensAmount) <= 0}
                  onClick={async () => {
                    const v = parseFloat(addTokensAmount)
                    if (!token || isNaN(v) || v <= 0) return
                    setTokenLoading("add")
                    setTokenMessage(null)
                    try {
                      const url = `${API_BASE}/admin/users/${uid}/tokens/add`
                      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ amount: v }) })
                      const data = await res.json().catch(() => ({}))
                      if (!res.ok) {
                        const detail = typeof data?.detail === "string" ? data.detail : Array.isArray(data?.detail) ? data.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ") : data?.detail ?? ""
                        const hint = res.status === 404
                          ? " Backend may be missing this route or not running. Start with: python -m uvicorn main:app --host 127.0.0.1 --port 8000"
                          : res.status === 403
                            ? " Check you are signed in as the admin user (ADMIN_EMAIL in .env)."
                            : ""
                        setTokenMessage({ type: "error", text: `Add tokens failed: ${res.status} ${res.statusText}. ${detail || "No details"}${hint} [POST ${url}]` })
                        return
                      }
                      setAddTokensAmount("")
                      setTokenMessage({ type: "success", text: `Added ${v} tokens. New balance: ${data.tokens_remaining ?? "—"}` })
                      const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } })
                      if (r.ok) setOverview(await r.json())
                    } catch (err) {
                      const msg = err instanceof Error ? err.message : String(err)
                      setTokenMessage({ type: "error", text: `Add tokens request failed: ${msg}. Check backend is running at ${API_BASE} (python -m uvicorn main:app --host 127.0.0.1 --port 8000).` })
                    } finally {
                      setTokenLoading(null)
                    }
                  }}
                >
                  {tokenLoading === "add" ? "Adding…" : "Add tokens"}
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  placeholder="Amount to deduct"
                  className="w-28"
                  min={0}
                  step={1}
                  value={deductTokensAmount}
                  onChange={(e) => { setDeductTokensAmount(e.target.value); setTokenMessage(null) }}
                  disabled={editsDisabled}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={editsDisabled || !deductTokensAmount.trim() || parseFloat(deductTokensAmount) <= 0}
                  onClick={async () => {
                    const v = parseFloat(deductTokensAmount)
                    if (!token || isNaN(v) || v <= 0) return
                    setTokenLoading("deduct")
                    setTokenMessage(null)
                    try {
                      const url = `${API_BASE}/admin/users/${uid}/tokens/deduct`
                      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ amount: v }) })
                      const data = await res.json().catch(() => ({}))
                      if (!res.ok) {
                        const detail = typeof data?.detail === "string" ? data.detail : Array.isArray(data?.detail) ? data.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ") : data?.detail ?? ""
                        const hint = res.status === 404
                          ? " Backend may be missing this route or not running. Start with: python -m uvicorn main:app --host 127.0.0.1 --port 8000"
                          : res.status === 403
                            ? " Check you are signed in as the admin user (ADMIN_EMAIL in .env)."
                            : ""
                        setTokenMessage({ type: "error", text: `Deduct tokens failed: ${res.status} ${res.statusText}. ${detail || "No details"}${hint} [POST ${url}]` })
                        return
                      }
                      setDeductTokensAmount("")
                      setTokenMessage({ type: "success", text: `Deducted ${v} tokens. New balance: ${data.tokens_remaining ?? "—"}` })
                      const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } })
                      if (r.ok) setOverview(await r.json())
                    } catch (err) {
                      const msg = err instanceof Error ? err.message : String(err)
                      setTokenMessage({ type: "error", text: `Deduct tokens request failed: ${msg}. Check backend is running at ${API_BASE} (python -m uvicorn main:app --host 127.0.0.1 --port 8000).` })
                    } finally {
                      setTokenLoading(null)
                    }
                  }}
                >
                  {tokenLoading === "deduct" ? "Deducting…" : "Deduct tokens"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>USDT Credit</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {overview.usdt_credit ? (
              <p>Balance: {String(overview.usdt_credit.usdt_credit)} · Earned: {String(overview.usdt_credit.total_earned)} · Withdrawn: {String(overview.usdt_credit.total_withdrawn)}</p>
            ) : (
              <p>No USDT credit row.</p>
            )}
            {usdtMessage && (
              <p className={`mt-2 text-xs break-words whitespace-pre-wrap max-w-2xl ${usdtMessage.type === "success" ? "text-chart-1" : "text-destructive"}`}>{usdtMessage.text}</p>
            )}
            <div className="flex gap-2 mt-2">
              <Input type="number" placeholder="+ or - amount" className="w-28" value={adjustUsdt} onChange={(e) => { setAdjustUsdt(e.target.value); setUsdtMessage(null) }} disabled={editsDisabled} />
              <Button size="sm" type="button" disabled={editsDisabled || !token} onClick={async () => {
                const v = parseFloat(adjustUsdt); if (!token || isNaN(v)) return
                setActionLoading("adjust_usdt"); setUsdtMessage(null)
                try {
                  const res = await fetch(`${API_BASE}/admin/usdt-credit/${uid}/adjust`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ amount: v }) })
                  const data = await res.json().catch(() => ({}))
                  if (!res.ok) { setUsdtMessage({ type: "error", text: `USDT adjust failed: ${res.status}. ${typeof data?.detail === "string" ? data.detail : data?.detail ?? "No details"}` }); return }
                  setAdjustUsdt(""); setUsdtMessage({ type: "success", text: `Adjusted by ${v >= 0 ? "+" : ""}${v} USDT.` }); await refetchOverview()
                } finally { setActionLoading(null) }
              }}>{actionLoading === "adjust_usdt" ? "Saving…" : "Adjust"}</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>API key</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {(overview.api_key_status && overview.api_key_status.has_keys === true) ? "Keys set" : "No keys"}
            {apiKeyMessage && (
              <p className={`mt-2 text-xs break-words whitespace-pre-wrap max-w-2xl ${apiKeyMessage.type === "success" ? "text-chart-1" : "text-destructive"}`}>{apiKeyMessage.text}</p>
            )}
            {Boolean(overview.api_key_status?.has_keys) && (
              <Button size="sm" variant="destructive" className="ml-2 mt-1" type="button" disabled={editsDisabled || !token} onClick={async () => {
                if (!token || !confirm("Reset API keys?")) return
                setActionLoading("reset_keys"); setApiKeyMessage(null)
                try {
                  const res = await fetch(`${API_BASE}/admin/api-keys/${uid}/reset`, { method: "POST", headers: { Authorization: `Bearer ${token}` } })
                  const data = await res.json().catch(() => ({}))
                  if (!res.ok) { setApiKeyMessage({ type: "error", text: `Reset keys failed: ${res.status}. ${typeof data?.detail === "string" ? data.detail : data?.detail ?? "No details"}` }); return }
                  setApiKeyMessage({ type: "success", text: "API keys reset." }); await refetchOverview()
                } finally { setActionLoading(null) }
              }}>{actionLoading === "reset_keys" ? "Resetting…" : "Reset keys"}</Button>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader><CardTitle>Referral</CardTitle></CardHeader>
        <CardContent className="text-sm">
          {overview.referral ? (
            <p>Referrer: {String(overview.referral.referrer_email ?? "—")} (ID {String(overview.referral.referrer_id ?? "—")}) · Downlines: {String(overview.referral.downline_count ?? "—")}</p>
          ) : (
            <p>—</p>
          )}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader><CardTitle>Withdrawals</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-2">ID</th>
                  <th className="text-left py-2 px-2">Amount</th>
                  <th className="text-left py-2 px-2">Address</th>
                  <th className="text-left py-2 px-2">Status</th>
                  <th className="text-left py-2 px-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {(overview.withdrawals || []).map((w: Record<string, unknown>, i: number) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-2 px-2">{String(w.id)}</td>
                    <td className="py-2 px-2">{String(w.amount)}</td>
                    <td className="py-2 px-2 truncate max-w-[160px]">{String(w.address)}</td>
                    <td className="py-2 px-2">{String(w.status)}</td>
                    <td className="py-2 px-2">{w.created_at ? new Date(String(w.created_at)).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader><CardTitle>Deduction history</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto max-h-48">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-2">Time</th>
                  <th className="text-left py-2 px-2">Deducted</th>
                  <th className="text-left py-2 px-2">After</th>
                </tr>
              </thead>
              <tbody>
                {(overview.deduction_history || []).map((d: Record<string, unknown>, i: number) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-2 px-2">{String(d.timestamp)}</td>
                    <td className="py-2 px-2">{String(d.tokens_deducted)}</td>
                    <td className="py-2 px-2">{String(d.tokens_remaining_after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader><CardTitle>Audit entries (this user)</CardTitle></CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm max-h-48 overflow-y-auto">
            {(overview.audit_entries || []).map((a: Record<string, unknown>, i: number) => (
              <li key={i}>{String(a.ts)} — {String(a.action)} — {JSON.stringify(a.detail)}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
