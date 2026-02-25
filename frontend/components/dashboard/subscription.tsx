"use client"

import { useState, useEffect } from "react"
import { Crown, Users, Check, Loader2 } from "lucide-react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type Plan = "pro" | "expert"
type Interval = "monthly" | "yearly"

const PRO_MONTHLY = 15
const PRO_YEARLY = 162 // 15 * 12 * 0.9
const EXPERT_MONTHLY = 39
const EXPERT_YEARLY = 421 // 39 * 12 * 0.9

export function Subscription() {
  const t = useT()
  const userId = useCurrentUserId()
  const [interval, setInterval] = useState<Interval>("yearly")
  const [loading, setLoading] = useState<string | null>(null)
  const [planTier, setPlanTier] = useState<string>("trial")
  const [daysLeft, setDaysLeft] = useState<number | null>(null)

  useEffect(() => {
    if (userId == null) return
    let cancelled = false
    const run = async () => {
      try {
        const res = await fetch(`${API_BASE}/user-status/${userId}`)
        if (cancelled || !res.ok) return
        const data = await res.json()
        setPlanTier((data.plan_tier || "trial").toLowerCase())
        setDaysLeft(typeof data.trial_remaining_days === "number" ? data.trial_remaining_days : null)
      } catch {
        if (!cancelled) setDaysLeft(null)
      }
    }
    run()
    return () => { cancelled = true }
  }, [userId])

  const handleSubscribe = async (plan: Plan) => {
    const { getBackendToken } = await import("@/lib/auth")
    const token = typeof window !== "undefined" ? await getBackendToken() : null
    if (!token) {
      window.location.href = "/login"
      return
    }
    setLoading(plan)
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

  const isSubscribed = planTier !== "trial"
  const displayDaysLeft = isSubscribed && daysLeft !== null

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("subscription.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subscription.subtitle")}</p>
      </div>

      {displayDaysLeft && (
        <div className="rounded-xl border border-emerald/30 bg-emerald/5 px-4 py-3 text-sm text-foreground">
          {t("subscription.daysLeft", { n: daysLeft })}
        </div>
      )}

      {/* Billing toggle */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setInterval("monthly")}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            interval === "monthly" ? "bg-emerald text-primary-foreground" : "bg-secondary text-muted-foreground hover:text-foreground"
          }`}
        >
          {t("subscription.monthly")}
        </button>
        <button
          type="button"
          onClick={() => setInterval("yearly")}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            interval === "yearly" ? "bg-emerald text-primary-foreground" : "bg-secondary text-muted-foreground hover:text-foreground"
          }`}
        >
          {t("subscription.yearly")}
        </button>
        <span className="rounded-full bg-emerald/20 px-2.5 py-0.5 text-xs font-semibold text-emerald">
          {t("subscription.save10")}
        </span>
      </div>

      {/* Plan cards */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* Pro Plan */}
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
            <span className="text-3xl font-bold text-foreground">
              ${interval === "monthly" ? PRO_MONTHLY : (PRO_YEARLY / 12).toFixed(0)}
            </span>
            <span className="text-sm text-muted-foreground">{t("subscription.perMonth")}</span>
          </div>
          <p className="text-xs text-muted-foreground">
            {interval === "yearly" ? t("subscription.billedYearly", { amount: `$${PRO_YEARLY}` }) : "\u00A0"}
          </p>
          <ul className="mt-5 space-y-3">
            {[t("subscription.featureLimit50"), t("subscription.featureRebalance30"), t("subscription.featureAnalytics"), t("subscription.featureEmailNotif"), t("subscription.featurePrioritySupport")].map((text, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-foreground">
                <Check className="h-4 w-4 shrink-0 text-emerald" />
                {text}
              </li>
            ))}
          </ul>
          <button
            onClick={() => handleSubscribe("pro")}
            disabled={!!loading}
            className="mt-6 w-full rounded-xl bg-emerald py-3 text-sm font-semibold text-primary-foreground hover:bg-emerald/90 disabled:opacity-50"
          >
            {loading === "pro" ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : t("subscription.subscribePro")}
          </button>
        </div>

        {/* Expert Plan */}
        <div className="rounded-2xl border border-border bg-card p-6 shadow-md">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg font-bold text-foreground">{t("subscription.expertPlan")}</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t("subscription.expertAudience")}</p>
          <div className="mt-4 flex items-baseline gap-1">
            <span className="text-3xl font-bold text-foreground">
              ${interval === "monthly" ? EXPERT_MONTHLY : (EXPERT_YEARLY / 12).toFixed(0)}
            </span>
            <span className="text-sm text-muted-foreground">{t("subscription.perMonth")}</span>
          </div>
          <p className="text-xs text-muted-foreground">
            {interval === "yearly" ? t("subscription.billedYearly", { amount: `$${EXPERT_YEARLY}` }) : "\u00A0"}
          </p>
          <ul className="mt-5 space-y-3">
            {[t("subscription.featureLimit250"), t("subscription.featureRebalance3"), t("subscription.featureAllAnalytics"), t("subscription.featureRealtimeNotif"), t("subscription.featurePrioritySupport"), t("subscription.featureCustomStrategies"), t("subscription.featureRiskMgmt")].map((text, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-foreground">
                <Check className="h-4 w-4 shrink-0 text-emerald" />
                {text}
              </li>
            ))}
          </ul>
          <button
            onClick={() => handleSubscribe("expert")}
            disabled={!!loading}
            className="mt-6 w-full rounded-xl border-2 border-emerald bg-transparent py-3 text-sm font-semibold text-emerald hover:bg-emerald/10 disabled:opacity-50"
          >
            {loading === "expert" ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : t("subscription.subscribeExpert")}
          </button>
        </div>
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
