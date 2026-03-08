"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { signIn } from "next-auth/react"
import { useT } from "@/lib/i18n"
import { PublicLayoutHeader, PublicLayoutFooter } from "@/components/landing/public-layout"
import { ArrowLeft, Link2, Zap, TrendingUp, BookOpen, Cpu, AlertTriangle } from "lucide-react"

export default function HowItWorksPage() {
  const t = useT()
  const params = useParams()
  const locale = (params?.locale as string) || "en"
  const homeHref = locale === "en" ? "/en" : `/${locale}`

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <PublicLayoutHeader />
      <main className="flex-1 max-w-3xl mx-auto w-full px-4 py-10">
        <Link
          href={homeHref}
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          {t("pages.backToHome")}
        </Link>
        <h1 className="text-2xl font-bold text-foreground mb-2">{t("howItWorks.title")}</h1>
        <p className="text-muted-foreground mb-10">{t("howItWorks.subtitle")}</p>

        {/* What is lending – intro block */}
        <section className="rounded-xl border border-border bg-card p-6 mb-10">
          <div className="flex gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <BookOpen className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-2">{t("howItWorks.whatIsLendingTitle")}</h2>
              <p className="text-muted-foreground">{t("howItWorks.whatIsLendingBody")}</p>
            </div>
          </div>
        </section>

        {/* Three steps */}
        <h2 className="text-xl font-semibold text-foreground mb-6">{t("howItWorks.step1Title")} → {t("howItWorks.step2Title")} → {t("howItWorks.step3Title")}</h2>
        <div className="space-y-10">
          <div className="flex gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Link2 className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-2">{t("howItWorks.step1Title")}</h3>
              <p className="text-muted-foreground">{t("howItWorks.step1Desc")}</p>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Zap className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-2">{t("howItWorks.step2Title")}</h3>
              <p className="text-muted-foreground">{t("howItWorks.step2Desc")}</p>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <TrendingUp className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-2">{t("howItWorks.step3Title")}</h3>
              <p className="text-muted-foreground">{t("howItWorks.step3Desc")}</p>
            </div>
          </div>
        </div>

        {/* How the bot works – strategy */}
        <section className="rounded-xl border border-border bg-muted/30 p-6 mt-10">
          <div className="flex gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Cpu className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-2">{t("howItWorks.strategyTitle")}</h2>
              <p className="text-muted-foreground">{t("howItWorks.strategyBody")}</p>
            </div>
          </div>
        </section>

        {/* Risk notice */}
        <section className="rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/50 dark:bg-amber-950/20 p-6 mt-10">
          <div className="flex gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-2">{t("howItWorks.riskTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("howItWorks.riskBody")}</p>
            </div>
          </div>
        </section>

        <div className="mt-12 text-center">
          <button
            type="button"
            onClick={() => void signIn("google", { callbackUrl: "/dashboard" })}
            className="rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {t("howItWorks.cta")}
          </button>
        </div>
      </main>
      <PublicLayoutFooter />
    </div>
  )
}
