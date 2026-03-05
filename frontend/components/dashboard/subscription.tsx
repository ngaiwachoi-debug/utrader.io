"use client"

import { useState, useEffect } from "react"
import { Crown, Users, Zap, Check, Loader2, ChevronDown, ChevronUp, Coins, ArrowDownCircle } from "lucide-react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useDeductionMultiplier, useDashboardData } from "@/lib/dashboard-data-context"
import { getBackendToken } from "@/lib/auth"
import { calculateTotalBudget, calculateUsagePercentage } from "@/lib/calculateTokenUsage"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"
const SHOW_DEV_BILLING = process.env.NEXT_PUBLIC_SHOW_DEV_BILLING === "true"

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
const PRESET_USD = [10, 25, 50]
const TOKENS_PER_USD = 100

type TokenBalanceState = {
  tokens_remaining: number
  total_tokens_added: number
  total_tokens_deducted: number
}

export function Subscription() {
  const t = useT()
  const userId = useCurrentUserId()
  const deductionMultiplier = useDeductionMultiplier()
  const { getUserStatus, getWallets, getTokenBalance } = useDashboardData()
  const id = userId ?? 0
  const [loading, setLoading] = useState<string | null>(null)
  const [planTier, setPlanTier] = useState<string>("trial")
  const [tokenBalance, setTokenBalance] = useState<TokenBalanceState | null>(null)
  const [tokenBalanceLoading, setTokenBalanceLoading] = useState(true)
  const [tokenBalanceError, setTokenBalanceError] = useState<string | null>(null)
  const [interval, setInterval] = useState<Interval>("monthly")
  const [addTokensUsd, setAddTokensUsd] = useState<string>("")
  const [loadingTokens, setLoadingTokens] = useState(false)
  const [depositMessage, setDepositMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [bypassPayment, setBypassPayment] = useState(false)
  const [faqOpen, setFaqOpen] = useState<string | null>(null)

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

  const handleSubscribe = async (plan: Plan, planInterval: Interval) => {
    const { getBackendToken } = await import("@/lib/auth")
    const token = typeof window !== "undefined" ? await getBackendToken() : null
    if (!token) {
      window.location.href = "/login"
      return
    }
    const loadingKey = planInterval === "yearly" ? `${plan}_yearly` : plan
    setLoading(loadingKey)
    try {
      if (bypassPayment) {
        const res = await fetch(`${API_BASE}/api/v1/subscription/bypass`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          credentials: "include",
          body: JSON.stringify({ plan, interval: planInterval }),
        })
        const data = await res.json().catch(() => ({}))
        if (res.ok && data.status === "success") {
          setDepositMessage({ type: "success", text: data.message ?? `${data.tokens_awarded} tokens added.` })
          if (userId != null) {
            const balanceRes = await fetch(`${API_BASE}/api/v1/users/me/token-balance`, { credentials: "include", headers: { Authorization: `Bearer ${token}` } })
            if (balanceRes.ok) {
              const bal = await balanceRes.json()
              setTokenBalance({ tokens_remaining: Number(bal.tokens_remaining) ?? 0, total_tokens_added: Number(bal.total_tokens_added) ?? 0, total_tokens_deducted: Number(bal.total_tokens_deducted) ?? 0 })
              setTokenBalanceError(null)
            }
            getUserStatus(id).refetch()
            getWallets(id).refetch()
            getTokenBalance(id).refetch()
          }
        } else {
          alert(data.detail ?? data.message ?? "Subscription bypass failed.")
        }
        setLoading(null)
        return
      }
      const res = await fetch(`${API_BASE}/api/create-checkout-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        credentials: "include",
        body: JSON.stringify({ plan, interval: planInterval }),
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

  const handlePurchaseTokens = async () => {
    const raw = addTokensUsd.trim()
    if (raw === "" || !/^-?\d*\.?\d+$/.test(raw)) {
      setDepositMessage({ type: "error", text: t("subscription.validUsd") })
      return
    }
    const amount = parseFloat(raw)
    if (!Number.isFinite(amount)) {
      setDepositMessage({ type: "error", text: t("subscription.validUsd") })
      return
    }
    if (amount < 1) {
      setDepositMessage({ type: "error", text: t("subscription.minDeposit") })
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
      if (!bypassPayment) {
        const res = await fetch(`${API_BASE}/api/create-checkout-session-tokens`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          credentials: "include",
          body: JSON.stringify({ amount_usd: amount }),
        })
        const data = await res.json().catch(() => ({}))
        if (res.ok && data.url) {
          window.location.href = data.url
          return
        }
        setDepositMessage({
          type: "error",
          text: (data.detail as string) || (data.message as string) || "Unable to start checkout. Please try again.",
        })
        setLoadingTokens(false)
        return
      }
      const res = await fetch(`${API_BASE}/api/v1/tokens/deposit`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        credentials: "include",
        body: JSON.stringify({ usd_amount: amount, bypass_payment: true }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.status === "success" && data.tokens_to_award != null) {
        setDepositMessage({
          type: "success",
          text: `${data.tokens_to_award} tokens added.`,
        })
        setAddTokensUsd("")
        if (userId != null) {
          const balanceRes = await fetch(`${API_BASE}/api/v1/users/me/token-balance`, {
            credentials: "include",
            headers: { Authorization: `Bearer ${token}` },
          })
          if (balanceRes.ok) {
            const bal = await balanceRes.json()
            setTokenBalance({
              tokens_remaining: Number(bal.tokens_remaining) ?? 0,
              total_tokens_added: Number(bal.total_tokens_added) ?? 0,
              total_tokens_deducted: Number(bal.total_tokens_deducted) ?? 0,
            })
            setTokenBalanceError(null)
          }
          getUserStatus(id).refetch()
          getWallets(id).refetch()
          getTokenBalance(id).refetch()
        }
      } else {
        setDepositMessage({
          type: "error",
          text: (data.message as string) || "Validation failed",
        })
      }
    } catch (e) {
      setDepositMessage({ type: "error", text: "Network error. Please try again." })
    } finally {
      setLoadingTokens(false)
    }
  }

  const addTokenAmount = (value: number) => setAddTokensUsd(String(value))
  const parsedUsd = addTokensUsd.trim() === "" ? 0 : parseFloat(addTokensUsd)
  const previewTokens = Number.isFinite(parsedUsd) && parsedUsd >= 1 ? Math.floor(parsedUsd * TOKENS_PER_USD) : 0

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("subscription.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subscription.subtitle")}</p>

        {/* Pay As You Go — top of page */}
        <div className="mt-4 rounded-xl border border-border bg-card p-5">
          <h3 className="text-base font-semibold text-foreground">{t("subscription.addTokens")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("subscription.addTokensDesc")}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {PRESET_USD.map((amount) => (
              <button
                key={amount}
                type="button"
                onClick={() => {
                  addTokenAmount(amount)
                  setDepositMessage(null)
                }}
                className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                  addTokensUsd === String(amount)
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border bg-background text-foreground hover:bg-muted/50"
                }`}
              >
                ${amount}
              </button>
            ))}
          </div>
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
            {SHOW_DEV_BILLING && (
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input type="checkbox" checked={bypassPayment} onChange={(e) => setBypassPayment(e.target.checked)} />
                {t("subscription.bypassPaymentDev")}
              </label>
            )}
            <button
              onClick={handlePurchaseTokens}
              disabled={loadingTokens}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {loadingTokens ? (
                <>
                  <Loader2 className="mr-1.5 inline h-4 w-4 animate-spin" />
                  {t("subscription.calculatingTokens")}
                </>
              ) : (
                t("subscription.purchaseTokens")
              )}
            </button>
          </div>
          {previewTokens > 0 && (
            <p className="mt-2 text-sm text-muted-foreground">
              {t("subscription.addTokensPreview", { n: previewTokens })}
            </p>
          )}
          {depositMessage && (
            <p
              className={`mt-2 text-sm ${depositMessage.type === "success" ? "text-primary" : "text-destructive"}`}
            >
              {depositMessage.text}
            </p>
          )}
        </div>
      </div>

      {/* Balance hero */}
      {tokenBalanceLoading && tokenBalance == null && !tokenBalanceError && (
        <div className="rounded-xl border border-border bg-card px-5 py-6">
          <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          <div className="mt-3 h-2 w-full rounded-full bg-muted animate-pulse" />
          <p className="mt-2 text-xs text-muted-foreground">…</p>
        </div>
      )}
      {tokenBalance != null && (() => {
        const totalBudget = calculateTotalBudget(tokenBalance.total_tokens_added)
        const used = tokenBalance.total_tokens_deducted
        const pct = calculateUsagePercentage(used, totalBudget)
        const remaining = tokenBalance.tokens_remaining
        const runningLow = totalBudget > 0 && (remaining < totalBudget * 0.2 || remaining < 50)
        return (
          <div className="rounded-xl border border-border bg-card px-5 py-6 shadow-sm">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("subscription.balanceRemaining")}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums text-foreground">{Math.round(remaining)}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("subscription.usedOfTotal", { used: Math.round(used), total: Math.round(totalBudget) })}
            </p>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
              />
            </div>
            {runningLow && (
              <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">
                {t("subscription.runningLow")}
              </p>
            )}
          </div>
        )
      })()}

      {/* Plans */}
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t("subscription.plansSection")}</h2>
        <div className="mt-2 flex gap-2 rounded-lg bg-muted/30 p-1">
          <button
            type="button"
            onClick={() => setInterval("monthly")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              interval === "monthly" ? "bg-background text-foreground shadow" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t("subscription.monthly")}
          </button>
          <button
            type="button"
            onClick={() => setInterval("yearly")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              interval === "yearly" ? "bg-background text-foreground shadow" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t("subscription.yearly")} ({t("subscription.save10")})
          </button>
        </div>
        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-3">
          {/* Pro */}
          <div className="relative rounded-2xl border-2 border-primary bg-card p-6 shadow-lg">
            <div className="absolute -top-px left-0 right-0 flex justify-center">
              <span className="flex items-center gap-1 rounded-b-md bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
                <Crown className="h-3 w-3" />
                {t("subscription.mostPopular")}
              </span>
            </div>
            <div className="mt-4">
              <h3 className="text-lg font-bold text-foreground">{t("subscription.proPlan")}</h3>
              <p className="text-xs text-muted-foreground">{t("subscription.proAudience")}</p>
            </div>
            <div className="mt-4 flex items-baseline gap-1">
              <span className="text-3xl font-bold text-foreground">
                ${interval === "monthly" ? PRO_USDT : PRO_YEARLY_USDT}
              </span>
              <span className="text-sm text-muted-foreground">
                {interval === "monthly" ? t("subscription.perMonth") : t("subscription.perYear")}
              </span>
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
                  <Check className="h-4 w-4 shrink-0 text-primary" />
                  {text}
                </li>
              ))}
            </ul>
            <div className="mt-6">
              <button
                onClick={() => handleSubscribe("pro", interval)}
                disabled={!!loading}
                className="w-full rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {loading === (interval === "yearly" ? "pro_yearly" : "pro") ? (
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                ) : (
                  t("subscription.subscribePro")
                )}
              </button>
            </div>
          </div>

          {/* AI Ultra */}
          <div className="rounded-2xl border border-border bg-card p-6 shadow-md">
            <div className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-muted-foreground" />
              <h3 className="text-lg font-bold text-foreground">{t("subscription.aiUltraPlan")}</h3>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("subscription.aiUltraAudience")}</p>
            <div className="mt-4 flex items-baseline gap-1">
              <span className="text-3xl font-bold text-foreground">
                ${interval === "monthly" ? AI_ULTRA_USDT : AI_ULTRA_YEARLY_USDT}
              </span>
              <span className="text-sm text-muted-foreground">
                {interval === "monthly" ? t("subscription.perMonth") : t("subscription.perYear")}
              </span>
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
                  <Check className="h-4 w-4 shrink-0 text-primary" />
                  {text}
                </li>
              ))}
            </ul>
            <div className="mt-6">
              <button
                onClick={() => handleSubscribe("ai_ultra", interval)}
                disabled={!!loading}
                className="w-full rounded-xl border-2 border-primary bg-transparent py-3 text-sm font-semibold text-primary hover:bg-primary/10 disabled:opacity-50"
              >
                {loading === (interval === "yearly" ? "ai_ultra_yearly" : "ai_ultra") ? (
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                ) : (
                  t("subscription.subscribeAiUltra")
                )}
              </button>
            </div>
          </div>

          {/* Whales */}
          <div className="rounded-2xl border border-border bg-card p-6 shadow-md">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-muted-foreground" />
              <h3 className="text-lg font-bold text-foreground">{t("subscription.whalesPlan")}</h3>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("subscription.whalesAudience")}</p>
            <div className="mt-4 flex items-baseline gap-1">
              <span className="text-3xl font-bold text-foreground">
                ${interval === "monthly" ? WHALES_USDT : WHALES_YEARLY_USDT}
              </span>
              <span className="text-sm text-muted-foreground">
                {interval === "monthly" ? t("subscription.perMonth") : t("subscription.perYear")}
              </span>
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
                  <Check className="h-4 w-4 shrink-0 text-primary" />
                  {text}
                </li>
              ))}
            </ul>
            <div className="mt-6">
              <button
                onClick={() => handleSubscribe("whales", interval)}
                disabled={!!loading}
                className="w-full rounded-xl border-2 border-primary bg-transparent py-3 text-sm font-semibold text-primary hover:bg-primary/10 disabled:opacity-50"
              >
                {loading === (interval === "yearly" ? "whales_yearly" : "whales") ? (
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                ) : (
                  t("subscription.subscribeWhales")
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Feature comparison table */}
        <div className="mt-8 overflow-hidden rounded-xl border border-border">
          <p className="border-b border-border bg-muted/30 px-4 py-2 text-xs font-semibold text-foreground">
            {t("subscription.comparePlans")}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[320px] text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/20">
                  <th className="px-4 py-2.5 font-medium text-foreground">{t("subscription.featureColumn")}</th>
                  <th className="px-4 py-2.5 font-medium text-foreground">{t("subscription.proPlan")}</th>
                  <th className="px-4 py-2.5 font-medium text-foreground">{t("subscription.aiUltraPlan")}</th>
                  <th className="px-4 py-2.5 font-medium text-foreground">{t("subscription.whalesPlan")}</th>
                </tr>
              </thead>
              <tbody className="text-muted-foreground">
                <tr className="border-b border-border/50">
                  <td className="px-4 py-2.5">{t("subscription.featureRebalance")}</td>
                  <td className="px-4 py-2.5">30 min</td>
                  <td className="px-4 py-2.5">3 min</td>
                  <td className="px-4 py-2.5">1 min</td>
                </tr>
                <tr className="border-b border-border/50">
                  <td className="px-4 py-2.5">{t("subscription.featureTokenCredit")}</td>
                  <td className="px-4 py-2.5">{PRO_TOKENS.toLocaleString()}</td>
                  <td className="px-4 py-2.5">{AI_ULTRA_TOKENS.toLocaleString()}</td>
                  <td className="px-4 py-2.5">{WHALES_TOKENS.toLocaleString()}</td>
                </tr>
                <tr className="border-b border-border/50">
                  <td className="px-4 py-2.5">{t("subscription.featureGemini")}</td>
                  <td className="px-4 py-2.5">—</td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                </tr>
                <tr className="border-b border-border/50">
                  <td className="px-4 py-2.5">{t("subscription.featureTerminal")}</td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                </tr>
                <tr className="border-b border-border/50">
                  <td className="px-4 py-2.5">{t("subscription.featureGeneralSupport")}</td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                </tr>
                <tr className="border-b border-border/50">
                  <td className="px-4 py-2.5">{t("subscription.featurePrioritySupport")}</td>
                  <td className="px-4 py-2.5">—</td>
                  <td className="px-4 py-2.5">—</td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5">{t("subscription.featureTrueRoi")}</td>
                  <td className="px-4 py-2.5">—</td>
                  <td className="px-4 py-2.5">—</td>
                  <td className="px-4 py-2.5"><Check className="inline h-4 w-4 text-primary" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* How tokens work — always visible, professional copy */}
      <div className="rounded-xl border border-border bg-muted/20 px-4 py-5">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-4">
          <Coins className="h-4 w-4 text-primary" />
          {t("subscription.howItWorks")}
        </h3>
        <p className="text-xs text-muted-foreground mb-4">
          {t("subscription.howItWorksLead")}
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex gap-3 rounded-lg bg-background/60 border border-border/50 p-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Coins className="h-4 w-4 text-primary" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground mb-0.5">{t("subscription.howEarnTitle")}</p>
              <p className="text-xs text-muted-foreground">{t("subscription.howEarnBody")}</p>
            </div>
          </div>
          <div className="flex gap-3 rounded-lg bg-background/60 border border-border/50 p-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
              <ArrowDownCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground mb-0.5">{t("subscription.howUseTitle")}</p>
              <p className="text-xs text-muted-foreground">{t("subscription.howUseBody", { multiplier: deductionMultiplier })}</p>
            </div>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-3">
          {t("subscription.howItWorksFooter")}
        </p>
      </div>

      {/* Trust footer */}
      <div className="rounded-xl border border-border bg-muted/30 px-4 py-4">
        <p className="text-xs text-muted-foreground">{t("subscription.terms")}</p>
        <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
          <li>{t("subscription.cancelAnytime")}</li>
          <li>{t("subscription.securePayment")}</li>
        </ul>

        {/* FAQ accordion */}
        <div className="mt-4 border-t border-border pt-4">
          <p className="mb-2 text-xs font-semibold text-foreground">{t("subscription.faqTitle")}</p>
          {[
            { id: "deduct", q: t("subscription.faqDeduct"), a: t("subscription.faqDeductA", { multiplier: deductionMultiplier }) },
            { id: "refresh", q: t("subscription.faqRefresh"), a: t("subscription.faqRefreshA") },
            { id: "refund", q: t("subscription.faqRefund"), a: t("subscription.faqRefundA") },
          ].map((faq) => (
            <div key={faq.id} className="border-b border-border/50 last:border-b-0">
              <button
                type="button"
                onClick={() => setFaqOpen(faqOpen === faq.id ? null : faq.id)}
                className="flex w-full items-center justify-between py-2 text-left text-xs font-medium text-foreground"
              >
                {faq.q}
                {faqOpen === faq.id ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
              {faqOpen === faq.id && <p className="pb-2 text-xs text-muted-foreground">{faq.a}</p>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
