"use client"

import { useState, useEffect, useCallback } from "react"
import { toast } from "sonner"
import { Copy, Wallet, UserPlus, Send, Loader2 } from "lucide-react"
import { getBackendToken } from "@/lib/auth"
import { useCurrentUserId } from "@/lib/current-user-context"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type ReferralInfo = {
  referral_code: string
  referrer_id: number | null
  referrer_email: string | null
  total_usdt_credit_earned: number
  usdt_withdraw_address?: string | null
}

type UsdtCredit = {
  usdt_credit: number
  locked_pending: number
  available: number
}

type WithdrawalRow = {
  id: number
  amount: number
  to_address?: string
  address?: string
  status: string
  created_at: string | null
  processed_at: string | null
  rejection_note?: string | null
}

type RewardHistoryRow = {
  created_at: string | null
  burning_user_id: number
  downline_email: string | null
  amount_usdt_credit: number
  level?: number
}

export function ReferralUsdt() {
  const userId = useCurrentUserId()
  const [referralInfo, setReferralInfo] = useState<ReferralInfo | null>(null)
  const [usdtCredit, setUsdtCredit] = useState<UsdtCredit | null>(null)
  const [withdrawals, setWithdrawals] = useState<WithdrawalRow[]>([])
  const [rewardHistory, setRewardHistory] = useState<RewardHistoryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [withdrawAmount, setWithdrawAmount] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  const fetchAll = useCallback(async () => {
    const token = await getBackendToken()
    if (!token || userId == null) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const [refRes, creditRes, histRes, rewardRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/user/referral-info`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE}/api/v1/user/usdt-credit`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE}/api/v1/user/usdt-withdraw-history`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE}/api/v1/user/referral-reward-history?limit=50`, { headers: { Authorization: `Bearer ${token}` } }),
      ])
      if (refRes.ok) setReferralInfo(await refRes.json())
      if (creditRes.ok) setUsdtCredit(await creditRes.json())
      if (histRes.ok) setWithdrawals(await histRes.json())
      if (rewardRes.ok) setRewardHistory(await rewardRes.json())
      else setRewardHistory([])
    } catch (e) {
      if (process.env.NODE_ENV === "development") console.error("Referral/USDT fetch error", e)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    if (userId != null) void fetchAll()
  }, [userId, fetchAll])

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
      void fetchAll()
    } catch {
      toast.error("Request failed")
    } finally {
      setSubmitting(false)
    }
  }

  if (loading && !referralInfo) {
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
      <h1 className="text-2xl font-bold text-foreground">Referral & USDT Credit</h1>

      {/* Referral Section */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground mb-4">
          <UserPlus className="h-5 w-5" />
          Referral Program
        </h2>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Your referral code:</span>
            <code className="rounded bg-secondary px-2 py-1 text-sm font-mono">{referralInfo?.referral_code || "—"}</code>
            <button
              type="button"
              onClick={copyCode}
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-secondary px-2 py-1 text-xs hover:bg-secondary/80"
            >
              <Copy className="h-3 w-3" /> Copy code
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Referral link:</span>
            <button
              type="button"
              onClick={copyReferralLink}
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-secondary px-2 py-1 text-xs hover:bg-secondary/80"
            >
              <Copy className="h-3 w-3" /> Copy link
            </button>
          </div>
          <p className="text-2xl font-bold text-emerald">
            Total USDT Credit earned: {(referralInfo?.total_usdt_credit_earned ?? 0).toFixed(4)} USDT
          </p>
        </div>
        {rewardHistory.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-foreground mb-2">Reward history</h3>
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-secondary/50">
                    <th className="text-left py-2 px-2">Date</th>
                    <th className="text-left py-2 px-2">Downline</th>
                    <th className="text-left py-2 px-2">Amount (USDT Credit)</th>
                  </tr>
                </thead>
                <tbody>
                  {rewardHistory.map((r, i) => (
                    <tr key={i} className="border-b border-border/50">
                      <td className="py-2 px-2 text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</td>
                      <td className="py-2 px-2">{r.downline_email ?? `User #${r.burning_user_id}`}</td>
                      <td className="py-2 px-2">{r.amount_usdt_credit.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* USDT Withdrawal Section */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground mb-4">
          <Wallet className="h-5 w-5" />
          USDT Credit Withdrawal
        </h2>
        <p className="text-sm text-muted-foreground mb-3">
          Withdrawals are processed manually by admin. Request will stay Pending until approved or rejected.
        </p>
        <div className="grid gap-2 mb-4">
          <p className="text-sm">
            <span className="text-muted-foreground">Balance:</span> {(usdtCredit?.usdt_credit ?? 0).toFixed(2)} USDT Credit
            {usdtCredit && usdtCredit.locked_pending > 0 && (
              <span className="ml-2 text-amber-600">(Locked pending: {usdtCredit.locked_pending.toFixed(2)})</span>
            )}
          </p>
          <p className="text-sm font-medium text-foreground">
            Available: {(usdtCredit?.available ?? 0).toFixed(2)} USDT Credit
          </p>
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
                className="rounded-lg bg-emerald px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-emerald/90 disabled:opacity-50 inline-flex items-center gap-2"
              >
                <Send className="h-4 w-4" /> Request withdrawal
              </button>
            </div>
          </>
        ) : (
          <p className="text-sm text-amber-600">Save a USDT withdrawal address in Settings before requesting a withdrawal.</p>
        )}

        {/* Withdrawal history */}
        <div className="mt-6">
          <h3 className="text-sm font-medium text-foreground mb-2">Withdrawal history</h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="text-left py-2 px-2">Date</th>
                  <th className="text-left py-2 px-2">Amount</th>
                  <th className="text-left py-2 px-2">Address</th>
                  <th className="text-left py-2 px-2">Status</th>
                  <th className="text-left py-2 px-2">Note</th>
                </tr>
              </thead>
              <tbody>
                {withdrawals.length === 0 ? (
                  <tr><td colSpan={5} className="py-4 px-2 text-center text-muted-foreground">No withdrawals yet</td></tr>
                ) : (
                  withdrawals.map((w) => (
                    <tr key={w.id} className={`border-b border-border/50 ${w.status === "pending" ? "bg-amber-500/10" : ""}`}>
                      <td className="py-2 px-2 text-muted-foreground">{w.created_at ? new Date(w.created_at).toLocaleString() : "—"}</td>
                      <td className="py-2 px-2">{w.amount.toFixed(2)}</td>
                      <td className="py-2 px-2 font-mono text-xs truncate max-w-[120px]" title={w.to_address ?? w.address}>{w.to_address ?? w.address}</td>
                      <td className="py-2 px-2">
                        <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                          w.status === "pending" ? "bg-amber-500/20 text-amber-700 dark:text-amber-400" :
                          w.status === "approved" ? "bg-emerald/20 text-emerald-700 dark:text-emerald-400" :
                          "bg-red-500/20 text-red-700 dark:text-red-400"
                        }`}>
                          {w.status}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-muted-foreground text-xs">{w.rejection_note ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Confirm modal */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => !submitting && setShowConfirm(false)}>
          <div className="rounded-xl border border-border bg-card p-5 max-w-sm w-full shadow-xl" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm text-foreground mb-4">
              Request withdrawal of <strong>{withdrawAmount} USDT Credit</strong>? The request will be pending until admin approval.
            </p>
            <div className="flex gap-2 justify-end">
              <button type="button" onClick={() => setShowConfirm(false)} disabled={submitting} className="rounded-lg border border-border px-4 py-2 text-sm">Cancel</button>
              <button type="button" onClick={handleWithdrawSubmit} disabled={submitting} className="rounded-lg bg-emerald px-4 py-2 text-sm text-primary-foreground inline-flex items-center gap-2">
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
