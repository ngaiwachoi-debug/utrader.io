"use client"

import { useState, useEffect } from "react"
import { Crown, Users, Zap, Check, Loader2 } from "lucide-react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { getBackendToken } from "@/lib/auth"

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

export function Subscription() {
  const t = useT()
  const userId = useCurrentUserId()
  const [loading, setLoading] = useState<string | null>(null) // plan key e.g. "pro" or "pro_yearly"
  const [planTier, setPlanTier] = useState<string>("trial")
  const [tokensRemaining, setTokensRemaining] = useState<number | null>(null)
  const [addTokensUsd, setAddTokensUsd] = useState<string>("")
  const [loadingTokens, setLoadingTokens] = useState(false)
  const [depositMessage, setDepositMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)

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
        const tr = data.tokens_remaining
        setTokensRemaining(typeof tr === "number" ? tr : null)
      } catch {
        if (!cancelled) setTokensRemaining(null)
      }
    }
    run()
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
        body: JSON.stringify({ usd_amount: amount }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.status === "success" && data.tokens_to_award != null) {
        setDepositMessage({
          type: "success",
          text: `${data.tokens_to_award} tokens will be added after payment`,
        })
        setAddTokensUsd("")
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

      {tokensRemaining !== null && (() => {
        const initial = planTier === "pro" ? PRO_TOKENS : planTier === "ai_ultra" ? AI_ULTRA_TOKENS : planTier === "whales" ? WHALES_TOKENS : 100
        const used = Math.max(0, initial - tokensRemaining)
        const pct = initial > 0 ? Math.min(100, (used / initial) * 100) : 0
        const runningLow = tokensRemaining < initial * 0.2 || tokensRemaining < 50
        return (
          <>
            <div className="rounded-xl border border-border bg-card px-4 py-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-foreground">{t("subscription.usageBar")}</span>
                <span className="text-muted-foreground">{Math.round(used)} / {initial} ({pct.toFixed(0)}%)</span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-emerald transition-all" style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {t("subscription.tokensRemaining", { n: Math.round(tokensRemaining) })}
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

      {/* Add tokens: custom USD → tokens (1 USD = 10 tokens), min $1 */}
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
            You get {Math.floor(Number(addTokensUsd) * 10)} tokens
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
