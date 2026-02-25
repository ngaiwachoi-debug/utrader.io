"use client"

import Link from "next/link"
import { useT } from "@/lib/i18n"
import { TrendingUp, Zap, Shield, BarChart3 } from "lucide-react"

export default function LandingPage() {
  const t = useT()

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
          Professional Bitfinex Lending Bot
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
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-lg bg-emerald px-6 py-3 text-base font-semibold text-primary-foreground hover:bg-emerald/90 transition-colors"
          >
            <Zap className="h-5 w-5" />
            {t("landing.startFreeTrial")}
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-6 py-3 text-base font-medium text-foreground hover:bg-secondary transition-colors"
          >
            <BarChart3 className="h-5 w-5" />
            {t("header.dashboard")}
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="px-4 lg:px-6 py-16 border-t border-border">
        <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="rounded-xl border border-border bg-card p-6 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald/10 text-emerald mb-4">
              <TrendingUp className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Live profit tracking</h3>
            <p className="text-sm text-muted-foreground">Real-time analytics and performance data</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald/10 text-emerald mb-4">
              <Shield className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Secure Access</h3>
            <p className="text-sm text-muted-foreground">Google OAuth — your keys stay secure</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald/10 text-emerald mb-4">
              <BarChart3 className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">ROI Optimization</h3>
            <p className="text-sm text-muted-foreground">Smart insights and automated rebalancing</p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-4 lg:px-6 py-16 border-t border-border text-center">
        <p className="text-muted-foreground mb-6">
          Join thousands of traders using uTrader.io to maximize their Bitfinex lending returns.
        </p>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-lg bg-emerald px-6 py-3 text-base font-semibold text-primary-foreground hover:bg-emerald/90 transition-colors"
        >
          {t("login.continueWithGoogle")}
        </Link>
      </section>

      <footer className="border-t border-border py-6 px-4 text-center text-xs text-muted-foreground">
        <Link href="/login" className="hover:text-foreground">Login</Link>
        {" · "}
        <Link href="/dashboard" className="hover:text-foreground">Dashboard</Link>
      </footer>
    </div>
  )
}
