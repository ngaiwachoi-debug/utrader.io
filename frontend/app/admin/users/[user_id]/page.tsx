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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type Overview = {
  user: Record<string, unknown>
  token_balance?: Record<string, unknown>
  usdt_credit?: Record<string, unknown>
  profit_snapshot?: Record<string, unknown>
  referral?: Record<string, unknown>
  api_key_status?: Record<string, unknown>
  withdrawals: Record<string, unknown>[]
  deduction_history: Record<string, unknown>[]
  audit_entries: Record<string, unknown>[]
}

export default function AdminUserDetailPage() {
  const params = useParams()
  const user_id = typeof params?.user_id === "string" ? params.user_id : ""
  const { data: session, status } = useSession()
  const [token, setToken] = useState<string | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [adjustTokens, setAdjustTokens] = useState("")
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
        <Link href="/admin" className="text-sm text-emerald hover:underline flex items-center gap-1 mb-4"><ArrowLeft className="h-4 w-4" /> Back to Admin</Link>
        <p className="text-destructive">{error || "User not found."}</p>
      </div>
    )
  }
  if (loading || !overview) {
    return <div className="min-h-screen flex items-center justify-center bg-background"><p className="text-sm text-muted-foreground">Loading user…</p></div>
  }

  const u = overview.user as Record<string, unknown>
  const uid = Number(user_id)

  return (
    <div className="min-h-screen bg-background p-4">
      <Link href="/admin" className="text-sm text-emerald hover:underline flex items-center gap-1 mb-4">
        <ArrowLeft className="h-4 w-4" /> Back to Admin
      </Link>

      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <h1 className="text-xl font-semibold text-foreground">
          User: {String(u.email)} (ID {user_id})
        </h1>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-1">
            <p>Plan: {String(u.plan_tier)} · Status: {String(u.status)} · Bot: {String(u.bot_status)}</p>
            <p>Pro expiry: {u.pro_expiry ? new Date(String(u.pro_expiry)).toLocaleString() : "—"}</p>
            <p>Created: {u.created_at ? new Date(String(u.created_at)).toLocaleString() : "—"}</p>
            <p>Referral code: {String(u.referral_code ?? "—")} · Referred by: {u.referred_by != null ? String(u.referred_by) : "—"}</p>
            <div className="flex flex-wrap gap-2 mt-2">
              <select className="rounded border border-border px-2 py-1 text-sm" value={setPlanTier} onChange={(e) => setSetPlanTier(e.target.value)}>
                <option value="">Set plan…</option>
                <option value="trial">trial</option>
                <option value="pro">pro</option>
                <option value="expert">expert</option>
                <option value="guru">guru</option>
              </select>
              <Button size="sm" disabled={!setPlanTier || !token} onClick={async () => { if (!token || !setPlanTier) return; await fetch(`${API_BASE}/admin/users/${uid}/set-plan`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ plan_tier: setPlanTier }) }); setSetPlanTier(""); const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } }); if (r.ok) setOverview(await r.json()) }}>Set plan</Button>
              <Input type="number" placeholder="Extend expiry (days)" className="w-36" value={extendDays} onChange={(e) => setExtendDays(e.target.value)} />
              <Button size="sm" disabled={!extendDays || !token} onClick={async () => { if (!token || extendDays === "") return; const days = parseInt(extendDays, 10); if (isNaN(days)) return; await fetch(`${API_BASE}/admin/users/${uid}/extend-expiry`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ days }) }); setExtendDays(""); const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } }); if (r.ok) setOverview(await r.json()) }}>Extend expiry</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Token balance</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {overview.token_balance ? (
              <p>Remaining: {String(overview.token_balance.tokens_remaining)} · Purchased: {String(overview.token_balance.purchased_tokens)} · Last gross used: {String(overview.token_balance.last_gross_usd_used)}</p>
            ) : (
              <p>No balance row.</p>
            )}
            <div className="flex gap-2 mt-2">
              <Input type="number" placeholder="Set tokens" className="w-28" value={adjustTokens} onChange={(e) => setAdjustTokens(e.target.value)} />
              <Button size="sm" onClick={async () => {
                const v = parseFloat(adjustTokens)
                if (!token || isNaN(v) || v < 0) return
                await fetch(`${API_BASE}/admin/users/${uid}`, { method: "PATCH", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ tokens_remaining: v }) })
                setAdjustTokens("")
                const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } })
                if (r.ok) setOverview(await r.json())
              }}>Apply</Button>
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
            <div className="flex gap-2 mt-2">
              <Input type="number" placeholder="+ or - amount" className="w-28" value={adjustUsdt} onChange={(e) => setAdjustUsdt(e.target.value)} />
              <Button size="sm" onClick={async () => {
                const v = parseFloat(adjustUsdt)
                if (!token || isNaN(v)) return
                await fetch(`${API_BASE}/admin/usdt-credit/${uid}/adjust`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ amount: v }) })
                setAdjustUsdt("")
                const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } })
                if (r.ok) setOverview(await r.json())
              }}>Adjust</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>API key</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {overview.api_key_status?.has_keys ? "Keys set" : "No keys"}
            {overview.api_key_status?.has_keys && (
              <Button size="sm" variant="destructive" className="ml-2" onClick={async () => {
                if (!token || !confirm("Reset API keys?")) return
                await fetch(`${API_BASE}/admin/api-keys/${uid}/reset`, { method: "POST", headers: { Authorization: `Bearer ${token}` } })
                const r = await fetch(`${API_BASE}/admin/users/${user_id}/overview`, { headers: { Authorization: `Bearer ${token}` } })
                if (r.ok) setOverview(await r.json())
              }}>Reset keys</Button>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader><CardTitle>Referral</CardTitle></CardHeader>
        <CardContent className="text-sm">
          {overview.referral ? (
            <p>Referrer: {String(overview.referral.referrer_email ?? "—")} (ID {overview.referral.referrer_id ?? "—"}) · Downlines: {String(overview.referral.downline_count)}</p>
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
