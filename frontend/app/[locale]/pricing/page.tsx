"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { signIn } from "next-auth/react"
import { useT } from "@/lib/i18n"
import { PublicLayoutHeader, PublicLayoutFooter } from "@/components/landing/public-layout"
import { ArrowLeft, Check, Coins, Percent, Users, FileText, LayoutGrid } from "lucide-react"

const PLANS = [
  { id: "pro", nameKey: "pricing.proName", priceKey: "pricing.proPrice", descKey: "pricing.proDesc", featuresKey: "pricing.proFeatures" },
  { id: "aiUltra", nameKey: "pricing.aiUltraName", priceKey: "pricing.aiUltraPrice", descKey: "pricing.aiUltraDesc" },
  { id: "whales", nameKey: "pricing.whalesName", priceKey: "pricing.whalesPrice", descKey: "pricing.whalesDesc" },
] as const

function Slide({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-border bg-card p-6 sm:p-8 lg:p-10 ${className}`}>
      {children}
    </section>
  )
}

function SlideTitle({ icon: Icon, title, subtitle }: { icon: React.ElementType; title: string; subtitle: string }) {
  return (
    <>
      <div className="flex items-center gap-2 mb-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <h2 className="text-xl font-bold text-foreground">{title}</h2>
      </div>
      <p className="text-muted-foreground mb-6 max-w-2xl">{subtitle}</p>
    </>
  )
}

export default function PricingPage() {
  const t = useT()
  const params = useParams()
  const locale = (params?.locale as string) || "en"
  const homeHref = locale === "en" ? "/en" : `/${locale}`

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <PublicLayoutHeader />
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-10 space-y-8">
        <Link
          href={homeHref}
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft className="h-4 w-4" />
          {t("pages.backToHome")}
        </Link>

        {/* Slide 1: Title */}
        <div className="text-center pb-4">
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground mb-2">{t("pricing.title")}</h1>
          <p className="text-muted-foreground mb-1">{t("pricing.subtitle")}</p>
          <p className="text-sm text-muted-foreground">{t("pricing.freeTrialNote")}</p>
        </div>

        {/* Slide 2: Plan cards */}
        <Slide className="bg-muted/20">
          <SlideTitle icon={LayoutGrid} title={t("pricing.slidePlansTitle")} subtitle={t("pricing.slidePlansSub")} />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {PLANS.map((plan) => (
              <div
                key={plan.id}
                className="rounded-xl border border-border bg-background p-5 flex flex-col"
              >
                <h3 className="text-lg font-semibold text-foreground">{t(plan.nameKey)}</h3>
                <p className="mt-1 text-2xl font-bold text-primary">
                  {t(plan.priceKey)}
                  <span className="text-sm font-normal text-muted-foreground">{t("pricing.perMonth")}</span>
                </p>
                <p className="mt-2 text-sm text-muted-foreground">{t(plan.descKey)}</p>
                {"featuresKey" in plan && (
                  <p className="mt-3 text-xs text-muted-foreground flex items-center gap-2">
                    <Check className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                    {t((plan as { featuresKey?: string }).featuresKey || "")}
                  </p>
                )}
                <div className="mt-6 flex-1" />
                <button
                  type="button"
                  onClick={() => void signIn("google", { callbackUrl: "/dashboard" })}
                  className="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  {t("pricing.cta")}
                </button>
              </div>
            ))}
          </div>
        </Slide>

        {/* Slide 3: Compare to typical monthly plans */}
        <Slide>
          <SlideTitle
            icon={FileText}
            title={t("pricing.slideCompareTitle")}
            subtitle={t("pricing.slideCompareSub")}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-xl border border-border bg-muted/30 p-5">
              <h3 className="font-semibold text-foreground mb-3">{t("pricing.compareOthersTitle")}</h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex gap-2">
                  <span className="text-muted-foreground">•</span>
                  {t("pricing.compareOthers1")}
                </li>
                <li className="flex gap-2">
                  <span className="text-muted-foreground">•</span>
                  {t("pricing.compareOthers2")}
                </li>
                <li className="flex gap-2">
                  <span className="text-muted-foreground">•</span>
                  {t("pricing.compareOthers3")}
                </li>
              </ul>
            </div>
            <div className="rounded-xl border-2 border-primary bg-primary/5 p-5">
              <h3 className="font-semibold text-primary mb-3">{t("pricing.compareUsTitle")}</h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex gap-2">
                  <Check className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  {t("pricing.compareUs1")}
                </li>
                <li className="flex gap-2">
                  <Check className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  {t("pricing.compareUs2")}
                </li>
                <li className="flex gap-2">
                  <Check className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  {t("pricing.compareUs3")}
                </li>
              </ul>
            </div>
          </div>
        </Slide>

        {/* Slide 4: Pay As You Go — no hard cap */}
        <Slide className="bg-muted/20">
          <SlideTitle
            icon={Coins}
            title={t("pricing.slidePaygTitle")}
            subtitle={t("pricing.slidePaygSub")}
          />
          <ul className="space-y-3 text-sm text-muted-foreground max-w-2xl">
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.paygBullet1")}
            </li>
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.paygBullet2")}
            </li>
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.paygBullet3")}
            </li>
          </ul>
        </Slide>

        {/* Slide 5: Cost as % of profit */}
        <Slide>
          <SlideTitle
            icon={Percent}
            title={t("pricing.slidePercentTitle")}
            subtitle={t("pricing.slidePercentSub")}
          />
          <ul className="space-y-3 text-sm text-muted-foreground max-w-2xl">
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.percentBullet1")}
            </li>
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.percentBullet2")}
            </li>
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.percentBullet3")}
            </li>
          </ul>
        </Slide>

        {/* Slide 6: Built for small fund users */}
        <Slide className="bg-muted/20">
          <SlideTitle
            icon={Users}
            title={t("pricing.slideSmallTitle")}
            subtitle={t("pricing.slideSmallSub")}
          />
          <ul className="space-y-3 text-sm text-muted-foreground max-w-2xl">
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.smallBullet1")}
            </li>
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.smallBullet2")}
            </li>
            <li className="flex gap-3">
              <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              {t("pricing.smallBullet3")}
            </li>
          </ul>
        </Slide>

        {/* Slide 7: How tokens work in one slide */}
        <Slide>
          <SlideTitle
            icon={FileText}
            title={t("pricing.slideHowTitle")}
            subtitle={t("pricing.slideHowSub")}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-sm">
            <div className="rounded-lg border border-border bg-muted/30 p-4">
              <p className="font-medium text-foreground mb-1">{t("pricing.howGetLabel")}</p>
              <p className="text-muted-foreground">{t("pricing.howGet")}</p>
            </div>
            <div className="rounded-lg border border-border bg-muted/30 p-4">
              <p className="font-medium text-foreground mb-1">{t("pricing.howUseLabel")}</p>
              <p className="text-muted-foreground">{t("pricing.howUse")}</p>
            </div>
          </div>
        </Slide>

        {/* CTA */}
        <div className="text-center py-6">
          <button
            type="button"
            onClick={() => void signIn("google", { callbackUrl: "/dashboard" })}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {t("landing.startFreeTrial")}
          </button>
        </div>
      </main>
      <PublicLayoutFooter />
    </div>
  )
}
