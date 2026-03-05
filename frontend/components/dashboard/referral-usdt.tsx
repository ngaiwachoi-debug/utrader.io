"use client"

import { useState, useEffect } from "react"
import { toast } from "sonner"
import { Copy, Wallet, UserPlus, Send, Loader2, RefreshCw, Users, History } from "lucide-react"
import { getBackendToken } from "@/lib/auth"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useReferralData } from "@/lib/dashboard-data-context"
import { useT } from "@/lib/i18n"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"
const REFRESH_COOLDOWN_SEC = 15

const USDT_REASON_LABELS: Record<string, string> = {
  withdrawal: "Withdrawal",
  admin_adjust: "Admin adjustment",
  referral_earnings_purchase: "Referral rewards",
  referral_earnings: "Referral rewards",
}

function formatUsdtReason(reason: string): string {
  if (!reason) return "—"
  const normalized = reason.trim().toLowerCase()
  return USDT_REASON_LABELS[normalized] ?? reason.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export function ReferralUsdt() {
  const t = useT()
  const userId = useCurrentUserId()
  const id = userId ?? 0
  const referralData = useReferralData(id)
  const { data, loading, error, isRevalidating, refetch } = referralData
  const referralInfo = data?.referralInfo ?? null
  const usdtCredit = data?.usdtCredit ?? null
  const withdrawals = data?.withdrawals ?? []
  const rewardHistory = data?.rewardHistory ?? []
  const downline = data?.downline ?? []
  const usdtHistory = data?.usdtHistory ?? []

  const [withdrawAmount, setWithdrawAmount] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [tab, setTab] = useState<"usdt" | "referral">("usdt")
  const [refreshCooldownUntil, setRefreshCooldownUntil] = useState(0)
  const [refreshCooldownSec, setRefreshCooldownSec] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((refreshCooldownUntil - Date.now()) / 1000))
      setRefreshCooldownSec(remaining)
    }, 1000)
    return () => clearInterval(interval)
  }, [refreshCooldownUntil])

  const handleRefresh = () => {
    if (Date.now() < refreshCooldownUntil) return
    setRefreshCooldownUntil(Date.now() + REFRESH_COOLDOWN_SEC * 1000)
    void refetch()
  }

  const copyReferralLink = () => {
    const code = referralInfo?.referral_code
    if (!code) return
    const url = typeof window !== "undefined" ? `${window.location.origin}/?ref=${encodeURIComponent(code)}` : ""
    navigator.clipboard.writeText(url).then(() => toast.success("Referral link copied"))
  }

  const copyCode = () => {
    if (referralInfo?.referral_code) {
      navigator.clipboard.writeText(referralInfo.referral_code).then(() => toast.success("Code copied"))
    }
  }

  const handleWithdrawSubmit = async () => {
    const token = await getBackendToken()
    if (!token) return
    const amount = parseFloat(withdrawAmount)
    if (isNaN(amount) || amount < 1) {
      toast.error("Minimum withdrawal is 1 USDT Credit")
      return
    }
    if (usdtCredit && amount > usdtCredit.available) {
      toast.error("Insufficient available balance")
      return
    }
    setSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/user/usdt-withdraw`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ amount }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        toast.error(typeof data.detail === "string" ? data.detail : "Withdrawal request failed")
        return
      }
      toast.success("Withdrawal request submitted. It is pending until admin approval.")
      setWithdrawAmount("")
      setShowConfirm(false)
      void refetch()
    } catch {
      toast.error("Request failed")
    } finally {
      setSubmitting(false)
    }
  }

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const referralLink = typeof window !== "undefined" && referralInfo?.referral_code
    ? `${window.location.origin}/?ref=${encodeURIComponent(referralInfo.referral_code)}`
    : ""

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-foreground">Referral & USDT Credit</h1>
        <div className="flex items-center gap-2">
          {isRevalidating && data && (
            <span className="text-xs text-muted-foreground">Updating…</span>
          )}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={loading || refreshCooldownSec > 0}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading && !data ? "animate-spin" : ""}`} />
            {refreshCooldownSec > 0 ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Top row: summary stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Total USDT Credit earned</p>
          <p className="mt-1 text-2xl font-bold text-primary">{(referralInfo?.total_usdt_credit_earned ?? 0).toFixed(4)}</p>
          <p className="text-xs text-muted-foreground mt-0.5">From referrals (L1/L2/L3)</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">People signed up with your code</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{referralInfo?.referred_users_count ?? 0}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {(referralInfo?.referred_users_count ?? 0) === 0 ? "No one yet." : "Referred users"}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Available to withdraw</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{(usdtCredit?.available ?? 0).toFixed(2)}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {usdtCredit && usdtCredit.locked_pending > 0 ? `Locked pending: ${usdtCredit.locked_pending.toFixed(2)}` : "USDT Credit"}
          </p>
        </div>
      </div>

      <div className="flex gap-2 mt-3 border-b border-border pb-2">
        <button
          type="button"
          onClick={() => setTab("usdt")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === "usdt"
              ? "bg-primary text-primary-foreground"
              : "bg-secondary/50 text-muted-foreground hover:bg-secondary"
          }`}
        >
          USDT Credit
        </button>
        <button
          type="button"
          onClick={() => setTab("referral")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === "referral"
              ? "bg-primary text-primary-foreground"
              : "bg-secondary/50 text-muted-foreground hover:bg-secondary"
          }`}
        >
          Referral
        </button>
      </div>

      {tab === "referral" && (
      <>
      {/* Card: Share your code */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground mb-4">
          <UserPlus className="h-5 w-5" />
          Share your code
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Your referral code</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-secondary px-2 py-1 text-sm font-mono">{referralInfo?.referral_code || "—"}</code>
              <button
                type="button"
                onClick={copyCode}
                className="inline-flex items-center gap-1 rounded-lg border border-border bg-secondary px-2 py-1 text-xs hover:bg-secondary/80"
              >
                <Copy className="h-3 w-3" /> Copy code
              </button>
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Referral link</p>
            <button
              type="button"
              onClick={copyReferralLink}
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-secondary px-2 py-1 text-xs hover:bg-secondary/80"
            >
              <Copy className="h-3 w-3" /> Copy link
            </button>
          </div>
        </div>
      </div>

      {/* Card: Referred users */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground mb-2">
          <Users className="h-5 w-5" />
          Referred users
        </h2>
        <p className="text-xs text-muted-foreground mb-4">People who signed up with your referral code. &quot;USDT earned from them&quot; is the sum of L1 rewards from their purchases and token burns (same source as Referral rewards in USDT reward history).</p>
        {downline.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="text-left py-2.5 px-3">Referred user</th>
                  <th className="text-left py-2.5 px-3">Joined</th>
                  <th className="text-right py-2.5 px-3">USDT earned from them</th>
                </tr>
              </thead>
              <tbody>
                {downline.map((d) => (
                  <tr key={d.user_id} className="border-b border-border/50">
                    <td className="py-2.5 px-3 font-mono text-muted-foreground">{d.email_masked}</td>
                    <td className="py-2.5 px-3 text-muted-foreground">{d.created_at ? new Date(d.created_at).toLocaleDateString(undefined, { dateStyle: "medium" }) : "—"}</td>
                    <td className="py-2.5 px-3 text-right font-medium">{d.total_usdt_earned_from_them.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rounded-lg border border-border bg-secondary/30 py-4 px-4 text-sm text-muted-foreground text-center">
            No one has signed up with your code yet. Share your referral link to start earning.
          </p>
        )}
      </div>

      {/* Card: USDT activity history (rewards, withdrawals, admin adjusts) */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground mb-2">
          <History className="h-5 w-5" />
          USDT reward history
        </h2>
        <p className="text-xs text-muted-foreground mb-4">Your USDT Credit activity: referral earnings, withdrawals, and admin adjustments.</p>
        {usdtHistory.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="text-left py-2.5 px-3">Date</th>
                  <th className="text-right py-2.5 px-3">Amount</th>
                  <th className="text-left py-2.5 px-3">Reason</th>
                </tr>
              </thead>
              <tbody>
                {usdtHistory.map((r) => (
                  <tr key={r.id} className="border-b border-border/50">
                    <td className="py-2.5 px-3 text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—"}</td>
                    <td className="py-2.5 px-3 text-right font-medium">{r.amount >= 0 ? "+" : ""}{r.amount.toFixed(4)}</td>
                    <td className="py-2.5 px-3">{formatUsdtReason(r.reason)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rounded-lg border border-border bg-secondary/30 py-4 px-4 text-sm text-muted-foreground text-center">
            No USDT activity yet.
          </p>
        )}
      </div>
      </>
      )}

      {tab === "usdt" && (
      <>
      {/* Card: Balance & withdraw */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground mb-2">
          <Wallet className="h-5 w-5" />
          USDT Credit withdrawal
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Withdrawals are processed manually by admin. Request will stay Pending until approved or rejected.
        </p>
        <div className="grid gap-2 mb-4">
          <p className="text-sm">
            <span className="text-muted-foreground">Balance:</span> {(usdtCredit?.usdt_credit ?? 0).toFixed(2)} USDT Credit
            {usdtCredit && usdtCredit.locked_pending > 0 && (
              <span className="ml-2 text-amber-600">(Locked pending: {usdtCredit.locked_pending.toFixed(2)})</span>
            )}
          </p>
          <p className="text-sm font-medium text-foreground">Available: {(usdtCredit?.available ?? 0).toFixed(2)} USDT Credit</p>
        </div>
        {referralInfo?.usdt_withdraw_address ? (
          <>
            <p className="text-xs text-muted-foreground mb-2">Withdrawal address (saved in Settings): {referralInfo.usdt_withdraw_address}</p>
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Amount (min 1 USDT Credit)</label>
                <input
                  type="number"
                  min={1}
                  step={0.01}
                  value={withdrawAmount}
                  onChange={(e) => setWithdrawAmount(e.target.value)}
                  className="w-32 rounded-lg border border-border bg-secondary px-3 py-2 text-sm"
                  placeholder="0"
                />
              </div>
              <button
                type="button"
                onClick={() => setShowConfirm(true)}
                disabled={!withdrawAmount || parseFloat(withdrawAmount) < 1 || (usdtCredit != null && parseFloat(withdrawAmount) > usdtCredit.available)}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 inline-flex items-center gap-2"
              >
                <Send className="h-4 w-4" /> Request withdrawal
              </button>
            </div>
          </>
        ) : (
          <p className="text-sm text-amber-600">Save a USDT withdrawal address in Settings before requesting a withdrawal.</p>
        )}
      </div>

      {/* Card: Withdrawal history */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground mb-4">
          <History className="h-5 w-5" />
          Withdrawal history
        </h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-secondary/50">
                <th className="text-left py-2.5 px-3">Date</th>
                <th className="text-left py-2.5 px-3">Amount</th>
                <th className="text-left py-2.5 px-3">Address</th>
                <th className="text-left py-2.5 px-3">Status</th>
                <th className="text-left py-2.5 px-3">Note</th>
              </tr>
            </thead>
            <tbody>
              {withdrawals.length === 0 ? (
                <tr><td colSpan={5} className="py-4 px-3 text-center text-muted-foreground">No withdrawals yet</td></tr>
              ) : (
                withdrawals.map((w) => (
                  <tr key={w.id} className={`border-b border-border/50 ${w.status === "pending" ? "bg-amber-500/10" : ""}`}>
                    <td className="py-2.5 px-3 text-muted-foreground">{w.created_at ? new Date(w.created_at).toLocaleString() : "—"}</td>
                    <td className="py-2.5 px-3">{w.amount.toFixed(2)}</td>
                    <td className="py-2.5 px-3 font-mono text-xs truncate max-w-[120px]" title={w.to_address ?? w.address}>{w.to_address ?? w.address}</td>
                    <td className="py-2.5 px-3">
                      <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                        w.status === "pending" ? "bg-amber-500/20 text-amber-700 dark:text-amber-400" :
                        w.status === "approved" ? "bg-chart-1/20 text-chart-1" :
                        "bg-red-500/20 text-red-700 dark:text-red-400"
                      }`}>
                        {w.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-muted-foreground text-xs">{w.rejection_note ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      </>
      )}

      {/* Confirm modal */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => !submitting && setShowConfirm(false)}>
          <div className="rounded-xl border border-border bg-card p-5 max-w-sm w-full shadow-xl" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm text-foreground mb-4">
              Request withdrawal of <strong>{withdrawAmount} USDT Credit</strong>? The request will be pending until admin approval.
            </p>
            <div className="flex gap-2 justify-end">
              <button type="button" onClick={() => setShowConfirm(false)} disabled={submitting} className="rounded-lg border border-border px-4 py-2 text-sm">Cancel</button>
              <button type="button" onClick={handleWithdrawSubmit} disabled={submitting} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground inline-flex items-center gap-2">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
