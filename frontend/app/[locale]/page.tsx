"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { signIn } from "next-auth/react"
import { useT } from "@/lib/i18n"
import { setDevBackendToken } from "@/lib/auth"
import { TrendingUp, Zap, Shield, BarChart3 } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

export default function LandingPage() {
  const t = useT()
  const router = useRouter()
  const [devLoginLoading, setDevLoginLoading] = useState(false)
  const [devLoginError, setDevLoginError] = useState<string | null>(null)

  async function handleDevLoginAsChoiwangai() {
    setDevLoginError(null)
    setDevLoginLoading(true)
    try {
      const res = await fetch(`${API_BASE}/dev/login-as`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: "choiwangai@gmail.com" }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setDevLoginError(data.detail ?? `HTTP ${res.status}`)
        return
      }
      const token = data.token
      if (!token) {
        setDevLoginError("No token in response")
        return
      }
      setDevBackendToken(token)
      router.push("/dashboard")
    } catch (e) {
      setDevLoginError(e instanceof Error ? e.message : "Request failed")
    } finally {
      setDevLoginLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="flex h-14 items-center justify-between px-4 lg:px-6">
          <Link href="/" className="text-sm font-semibold text-foreground">
            uTrader<span className="text-emerald">.io</span>
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-secondary transition-colors"
            >
              {t("landing.login")}
            </Link>
            <Link
              href="/login"
              className="rounded-lg bg-emerald px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-emerald/90 transition-colors"
            >
              {t("landing.startFreeTrial")}
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="px-4 lg:px-6 py-16 lg:py-24 text-center">
        <p className="text-sm font-medium uppercase tracking-wider text-emerald mb-4">
          {t("landing.heroBadge")}
        </p>
        <h1 className="text-4xl lg:text-5xl font-bold text-foreground mb-4 max-w-3xl mx-auto">
          {t("landing.heroTitle")}
        </h1>
        <p className="text-2xl lg:text-3xl font-semibold text-emerald mb-6">
          {t("landing.heroSubtitle")}
        </p>
        <p className="text-muted-foreground max-w-2xl mx-auto mb-10">
          {t("landing.heroDesc")}
        </p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <button
            type="button"
            onClick={() => signIn("google", { callbackUrl: "/dashboard" })}
            className="inline-flex items-center gap-2 rounded-lg bg-[#10b981] px-6 py-3 text-base font-semibold text-white hover:bg-emerald/90 transition-colors"
          >
            <Zap className="h-5 w-5" />
            {t("login.signInWithGoogle")}
          </button>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-6 py-3 text-base font-medium text-foreground hover:bg-secondary transition-colors"
          >
            <BarChart3 className="h-5 w-5" />
            {t("header.dashboard")}
          </Link>
          <button
            type="button"
            onClick={handleDevLoginAsChoiwangai}
            disabled={devLoginLoading}
            className="inline-flex items-center gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-2 text-sm text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 transition-colors"
          >
            {devLoginLoading ? "…" : "Dev: Login as choiwangai@gmail.com"}
          </button>
        </div>
        {devLoginError && (
          <p className="mt-3 text-sm text-red-500">{devLoginError}</p>
        )}
      </section>

      {/* Features */}
      <section className="px-4 lg:px-6 py-16 border-t border-border">
        <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="rounded-xl border border-border bg-card p-6 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald/10 text-emerald mb-4">
              <TrendingUp className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">{t("landing.feature1Title")}</h3>
            <p className="text-sm text-muted-foreground">{t("landing.feature1Desc")}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald/10 text-emerald mb-4">
              <Shield className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">{t("landing.feature2Title")}</h3>
            <p className="text-sm text-muted-foreground">{t("landing.feature2Desc")}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald/10 text-emerald mb-4">
              <BarChart3 className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">{t("landing.feature3Title")}</h3>
            <p className="text-sm text-muted-foreground">{t("landing.feature3Desc")}</p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-4 lg:px-6 py-16 border-t border-border text-center">
        <p className="text-muted-foreground mb-6">
          {t("landing.ctaText")}
        </p>
        <button
          type="button"
          onClick={() => signIn("google", { callbackUrl: "/dashboard" })}
          className="inline-flex items-center gap-2 rounded-lg bg-[#10b981] px-6 py-3 text-base font-semibold text-white hover:bg-emerald/90 transition-colors"
        >
          {t("login.signInWithGoogle")}
        </button>
      </section>

      <footer className="border-t border-border py-6 px-4 text-center text-xs text-muted-foreground">
        <Link href="/login" className="hover:text-foreground">{t("landing.footerLogin")}</Link>
        {" · "}
        <Link href="/dashboard" className="hover:text-foreground">{t("landing.footerDashboard")}</Link>
      </footer>
    </div>
  )
}
