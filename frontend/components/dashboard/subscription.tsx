"use client"

import { useState, useEffect } from "react"
import { Crown, Users, Zap, Check, Loader2 } from "lucide-react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { getBackendToken } from "@/lib/auth"
import { calculateTotalBudget, calculateUsagePercentage } from "@/lib/calculateTokenUsage"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type Plan = "pro" | "ai_ultra" | "whales"
type Interval = "monthly" | "yearly"

const PRO_USDT = 20
const AI_ULTRA_USDT = 60
const WHALES_USDT = 200
const PRO_YEARLY_USDT = 192
const AI_ULTRA_YEARLY_USDT = 576
const WHALES_YEARLY_USDT = 1920
const PRO_TOKENS = 2000
const AI_ULTRA_TOKENS = 9000
const WHALES_TOKENS = 40000

type TokenBalanceState = {
  tokens_remaining: number
  total_tokens_added: number
  total_tokens_deducted: number
}

export function Subscription() {
  const t = useT()
  const userId = useCurrentUserId()
  const [loading, setLoading] = useState<string | null>(null) // plan key e.g. "pro" or "pro_yearly"
  const [planTier, setPlanTier] = useState<string>("trial")
  const [tokenBalance, setTokenBalance] = useState<TokenBalanceState | null>(null)
  const [tokenBalanceLoading, setTokenBalanceLoading] = useState(true)
  const [tokenBalanceError, setTokenBalanceError] = useState<string | null>(null)
  const [addTokensUsd, setAddTokensUsd] = useState<string>("")
  const [loadingTokens, setLoadingTokens] = useState(false)
  const [depositMessage, setDepositMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [bypassPayment, setBypassPayment] = useState(false)

  useEffect(() => {
    if (userId == null) return
    let cancelled = false
    const run = async () => {
      try {
        const token = await getBackendToken()
        const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
        const res = await fetch(`${API_BASE}/user-status/${userId}`, { credentials: "include", headers })
        if (cancelled || !res.ok) return
        const data = await res.json()
        setPlanTier((data.plan_tier || "trial").toLowerCase())
      } catch {
        /* ignore */
      }
    }
    run()
    return () => { cancelled = true }
  }, [userId])

  useEffect(() => {
    if (userId == null) {
      setTokenBalance(null)
      setTokenBalanceLoading(false)
      setTokenBalanceError(null)
      return
    }
    let cancelled = false
    const fetchTokenBalance = async () => {
      const token = await getBackendToken()
      if (!token) {
        if (!cancelled) setTokenBalanceLoading(false)
        return
      }
      try {
        const res = await fetch(`${API_BASE}/api/v1/users/me/token-balance`, {
          credentials: "include",
          headers: { Authorization: `Bearer ${token}` },
        })
        if (cancelled) return
        if (res.ok) {
          const data = await res.json()
          if (!cancelled) {
            setTokenBalance({
              tokens_remaining: Number(data.tokens_remaining) ?? 0,
              total_tokens_added: Number(data.total_tokens_added) ?? 0,
              total_tokens_deducted: Number(data.total_tokens_deducted) ?? 0,
            })
            setTokenBalanceError(null)
          }
        } else {
          if (!cancelled) setTokenBalanceError(t("settings.tokenDataContactSupport"))
        }
      } catch {
        if (!cancelled) setTokenBalanceError(t("settings.tokenUsageFailed"))
      } finally {
        if (!cancelled) setTokenBalanceLoading(false)
      }
    }
    setTokenBalanceLoading(true)
    fetchTokenBalance()
    return () => { cancelled = true }
  }, [userId])

  const handleSubscribe = async (plan: Plan, interval: Interval) => {
    const { getBackendToken } = await import("@/lib/auth")
    const token = typeof window !== "undefined" ? await getBackendToken() : null
    if (!token) {
      window.location.href = "/login"
      return
    }
    const loadingKey = interval === "yearly" ? `${plan}_yearly` : plan
    setLoading(loadingKey)
    try {
      const res = await fetch(`${API_BASE}/api/create-checkout-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        credentials: "include",
        body: JSON.stringify({ plan, interval }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.url) {
        window.location.href = data.url
        return
      }
      alert(data.detail || "Unable to start checkout. Please try again.")
    } catch (e) {
      alert("Network error. Please try again.")
    } finally {
      setLoading(null)
    }
  }

  const isSubscribed = planTier !== "trial" && planTier !== "free"

  const handlePurchaseTokens = async () => {
    const raw = addTokensUsd.trim()
    if (raw === "" || !/^-?\d*\.?\d+$/.test(raw)) {
      setDepositMessage({ type: "error", text: "Please enter a valid USD amount" })
      return
    }
    const amount = parseFloat(raw)
    if (!Number.isFinite(amount)) {
      setDepositMessage({ type: "error", text: "Please enter a valid USD amount" })
      return
    }
    if (amount < 1) {
      setDepositMessage({ type: "error", text: "Minimum deposit is $1" })
      return
    }
    const { getBackendToken } = await import("@/lib/auth")
    const token = typeof window !== "undefined" ? await getBackendToken() : null
    if (!token) {
      window.location.href = "/login"
      return
    }
    setDepositMessage(null)
    setLoadingTokens(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/tokens/deposit`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        credentials: "include",
        body: JSON.stringify({ usd_amount: amount, bypass_payment: bypassPayment }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.status === "success" && data.tokens_to_award != null) {
        setDepositMessage({
          type: "success",
          text: bypassPayment ? `${data.tokens_to_award} tokens added.` : `${data.tokens_to_award} tokens will be added after payment`,
        })
        setAddTokensUsd("")
        if (bypassPayment && userId != null) {
          const [statusRes, balanceRes] = await Promise.all([
            fetch(`${API_BASE}/user-status/${userId}`, { credentials: "include", headers: { Authorization: `Bearer ${token}` } }),
            fetch(`${API_BASE}/api/v1/users/me/token-balance`, { credentials: "include", headers: { Authorization: `Bearer ${token}` } }),
          ])
          if (balanceRes.ok) {
            const bal = await balanceRes.json()
            setTokenBalance({
              tokens_remaining: Number(bal.tokens_remaining) ?? 0,
              total_tokens_added: Number(bal.total_tokens_added) ?? 0,
              total_tokens_deducted: Number(bal.total_tokens_deducted) ?? 0,
            })
            setTokenBalanceError(null)
          }
        }
      } else {
        setDepositMessage({
          type: "error",
          text: (data.message as string) || "Validation failed",
        })
      }
      // TODO: Add Stripe checkout flow here (redirect to data.url when implemented)
      // if (res.ok && data.url) { window.location.href = data.url; return }
    } catch (e) {
      setDepositMessage({ type: "error", text: "Network error. Please try again." })
    } finally {
      setLoadingTokens(false)
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("subscription.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subscription.subtitle")}</p>
      </div>

      {/* Token usage: same data and logic as Settings (total_tokens_added, total_tokens_deducted, tokens_remaining) — show for all users */}
      {tokenBalanceLoading && tokenBalance == null && !tokenBalanceError && (
        <div className="rounded-xl border border-border bg-card px-4 py-4">
          <div className="h-2 w-full rounded-full bg-muted animate-pulse" />
          <p className="mt-2 text-xs text-muted-foreground">…</p>
        </div>
      )}
      {tokenBalanceError && (
        <div className="rounded-xl border border-border bg-card px-4 py-4">
          <p className="text-xs text-destructive">{tokenBalanceError}</p>
        </div>
      )}
      {tokenBalance != null && (() => {
        const totalBudget = calculateTotalBudget(tokenBalance.total_tokens_added)
        const used = tokenBalance.total_tokens_deducted
        const pct = calculateUsagePercentage(used, totalBudget)
        const remaining = tokenBalance.tokens_remaining
        const runningLow = totalBudget > 0 && (remaining < totalBudget * 0.2 || remaining < 50)
        return (
          <>
            <div className="rounded-xl border border-border bg-card px-4 py-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-foreground">{t("subscription.usageBar")}</span>
                <span className="text-muted-foreground">
                  {totalBudget > 0 ? `${Math.round(used)} / ${Math.round(totalBudget)} (${Math.round(pct)}%)` : `${Math.round(remaining)} tokens`}
                </span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-emerald transition-all" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {t("subscription.tokensRemaining", { n: Math.round(remaining) })}
              </p>
              {runningLow && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  {t("subscription.runningLow")}
                </p>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("subscription.tokenUsageRule")}
            </p>
          </>
        )
      })()}

      {/* Plan cards: Pro, AI Ultra, Whales */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {/* Pro — 20 USDT */}
        <div className="relative rounded-2xl border-2 border-emerald bg-card p-6 shadow-lg">
          <div className="absolute -top-px left-0 right-0 flex justify-center">
            <span className="flex items-center gap-1 rounded-b-md bg-emerald px-3 py-1 text-xs font-semibold text-primary-foreground">
              <Crown className="h-3 w-3" />
              {t("subscription.mostPopular")}
            </span>
          </div>
          <div className="mt-4">
            <h2 className="text-lg font-bold text-foreground">{t("subscription.proPlan")}</h2>
            <p className="text-xs text-muted-foreground">{t("subscription.proAudience")}</p>
          </div>
          <div className="mt-4 flex items-baseline gap-1">
            <span className="text-3xl font-bold text-foreground">${PRO_USDT}</span>
            <span className="text-sm text-muted-foreground">{t("subscription.perMonth")}</span>
          </div>
          <ul className="mt-5 space-y-3">
            {[
              t("subscription.featureTokens", { n: PRO_TOKENS }),
              t("subscription.featureRebalance30"),
              t("subscription.featureAnalytics"),
              t("subscription.featureEmailNotif"),
              t("subscription.featurePrioritySupport"),
            ].map((text, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-foreground">
                <Check className="h-4 w-4 shrink-0 text-emerald" />
                {text}
              </li>
            ))}
          </ul>
          <div className="mt-6 flex flex-col gap-2">
            <button
              onClick={() => handleSubscribe("pro", "monthly")}
              disabled={!!loading}
              className="w-full rounded-xl bg-emerald py-3 text-sm font-semibold text-primary-foreground hover:bg-emerald/90 disabled:opacity-50"
            >
              {loading === "pro" ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : t("subscription.subscribePro") + " (" + t("subscription.monthly") + ")"}
            </button>
            <button
              onClick={() => handleSubscribe("pro", "yearly")}
              disabled={!!loading}
              className="w-full rounded-xl border-2 border-emerald bg-transparent py-2.5 text-sm font-semibold text-emerald hover:bg-emerald/10 disabled:opacity-50"
            >
              {loading === "pro_yearly" ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : `$${PRO_YEARLY_USDT}/year ${t("subscription.save10")}`}
            </button>
          </div>
        </div>

        {/* AI Ultra — 60 USDT */}
        <div className="rounded-2xl border border-border bg-card p-6 shadow-md">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg font-bold text-foreground">{t("subscription.aiUltraPlan")}</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("subscription.aiUltraAudience")}</p>
          <div className="mt-4 flex items-baseline gap-1">
            <span className="text-3xl font-bold text-foreground">${AI_ULTRA_USDT}</span>
            <span className="text-sm text-muted-foreground">{t("subscription.perMonth")}</span>
          </div>
          <ul className="mt-5 space-y-3">
            {[
              t("subscription.featureTokens", { n: AI_ULTRA_TOKENS }),
              t("subscription.featureRebalance3"),
              t("subscription.featureAnalytics"),
              t("subscription.featureEmailNotif"),
              t("subscription.featureGemini"),
              t("subscription.featurePrioritySupport"),
            ].map((text, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-foreground">
                <Check className="h-4 w-4 shrink-0 text-emerald" />
                {text}
              </li>
            ))}
          </ul>
          <div className="mt-6 flex flex-col gap-2">
            <button
              onClick={() => handleSubscribe("ai_ultra", "monthly")}
              disabled={!!loading}
              className="w-full rounded-xl border-2 border-emerald bg-transparent py-3 text-sm font-semibold text-emerald hover:bg-emerald/10 disabled:opacity-50"
            >
              {loading === "ai_ultra" ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : t("subscription.subscribeAiUltra") + " (" + t("subscription.monthly") + ")"}
            </button>
            <button
              onClick={() => handleSubscribe("ai_ultra", "yearly")}
              disabled={!!loading}
              className="w-full rounded-xl border border-border py-2.5 text-sm font-semibold text-muted-foreground hover:bg-muted/50 disabled:opacity-50"
            >
              {loading === "ai_ultra_yearly" ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : `$${AI_ULTRA_YEARLY_USDT}/year ${t("subscription.save10")}`}
            </button>
          </div>
        </div>

        {/* Whales AI — 200 USDT */}
        <div className="rounded-2xl border border-border bg-card p-6 shadow-md">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg font-bold text-foreground">{t("subscription.whalesPlan")}</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("subscription.whalesAudience")}</p>
          <div className="mt-4 flex items-baseline gap-1">
            <span className="text-3xl font-bold text-foreground">${WHALES_USDT}</span>
            <span className="text-sm text-muted-foreground">{t("subscription.perMonth")}</span>
          </div>
          <ul className="mt-5 space-y-3">
            {[
              t("subscription.featureTokens", { n: WHALES_TOKENS }),
              t("subscription.featureRebalance1"),
              t("subscription.featureAnalytics"),
              t("subscription.featureEmailNotif"),
              t("subscription.featureGemini"),
              t("subscription.featureTerminal"),
              t("subscription.featurePrioritySupport"),
            ].map((text, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-foreground">
                <Check className="h-4 w-4 shrink-0 text-emerald" />
                {text}
              </li>
            ))}
          </ul>
          <div className="mt-6 flex flex-col gap-2">
            <button
              onClick={() => handleSubscribe("whales", "monthly")}
              disabled={!!loading}
              className="w-full rounded-xl border-2 border-emerald bg-transparent py-3 text-sm font-semibold text-emerald hover:bg-emerald/10 disabled:opacity-50"
            >
              {loading === "whales" ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : t("subscription.subscribeWhales") + " (" + t("subscription.monthly") + ")"}
            </button>
            <button
              onClick={() => handleSubscribe("whales", "yearly")}
              disabled={!!loading}
              className="w-full rounded-xl border border-border py-2.5 text-sm font-semibold text-muted-foreground hover:bg-muted/50 disabled:opacity-50"
            >
              {loading === "whales_yearly" ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : `$${WHALES_YEARLY_USDT}/year ${t("subscription.save10")}`}
            </button>
          </div>
        </div>
      </div>

      {/* Add tokens: 1 USD = 100 tokens, min $1 */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="text-sm font-semibold text-foreground">{t("subscription.addTokens")}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{t("subscription.addTokensDesc")}</p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[120px]">
            <label className="mb-1 block text-xs text-muted-foreground">{t("subscription.amountUsd")}</label>
            <input
              type="number"
              min={1}
              step={0.01}
              value={addTokensUsd}
              onChange={(e) => {
                setAddTokensUsd(e.target.value)
                setDepositMessage(null)
              }}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder="10"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={bypassPayment} onChange={(e) => setBypassPayment(e.target.checked)} />
            Bypass payment (dev)
          </label>
          <button
            onClick={handlePurchaseTokens}
            disabled={loadingTokens}
            className="rounded-lg bg-emerald px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-emerald/90 disabled:opacity-50"
          >
            {loadingTokens ? (
              <>
                <Loader2 className="mr-1.5 inline h-4 w-4 animate-spin" />
                Calculating tokens...
              </>
            ) : (
              t("subscription.purchaseTokens")
            )}
          </button>
        </div>
        {addTokensUsd && Number(addTokensUsd) >= 1 && !loadingTokens && (
          <p className="mt-2 text-xs text-muted-foreground">
            You get {Math.floor(Number(addTokensUsd) * 100)} tokens (1 USD = 100 tokens)
          </p>
        )}
        {depositMessage && (
          <p
            className={`mt-2 text-sm ${depositMessage.type === "success" ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}
          >
            {depositMessage.text}
          </p>
        )}
      </div>

      <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
        <p>{t("subscription.terms")}</p>
        <ul className="mt-2 list-inside list-disc space-y-0.5">
          <li>{t("subscription.cancelAnytime")}</li>
          <li>{t("subscription.securePayment")}</li>
        </ul>
      </div>
    </div>
  )
}
