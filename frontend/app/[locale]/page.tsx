"use client"

import Link from "next/link"
import { useParams, useSearchParams } from "next/navigation"
import { signIn } from "next-auth/react"
import { useT } from "@/lib/i18n"
import { PublicLayoutHeader, PublicLayoutFooter } from "@/components/landing/public-layout"
import { InstallAppButton } from "@/components/dashboard/install-app-button"
import { Zap, Shield, TrendingUp, BarChart3, Cpu, Layers, Activity, Bot, LineChart, Settings2, ArrowRight, CheckCircle2, Lock } from "lucide-react"
import { AaveStyleSection } from "@/components/landing/aave-style-section"
import { AnimateOnScroll } from "@/components/landing/animate-on-scroll"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"

const PENDING_REFERRAL_KEY = "pending_referral_code"

const FAQ_ITEMS = [
  { q: "faq.q1", a: "faq.a1" },
  { q: "faq.q2", a: "faq.a2" },
  { q: "faq.q3", a: "faq.a3" },
  { q: "faq.q4", a: "faq.a4" },
  { q: "faq.q5", a: "faq.a5" },
  { q: "faq.q6", a: "faq.a6" },
] as const

const STATS = [
  { value: "$120M+", label: "Total Volume Managed" },
  { value: "4,200+", label: "Active Users" },
  { value: "15% APR", label: "Average Yield" },
  { value: "99.9%", label: "Uptime" },
]

const WHY_CARDS = [
  { key: "1", icon: Cpu, iconBg: "bg-[#F0B90B]/15 text-[#F0B90B]", titleKey: "landing.whyCard1Title", descKey: "landing.whyCard1Desc" },
  { key: "2", icon: Layers, iconBg: "bg-emerald-500/15 text-emerald-400", titleKey: "landing.whyCard2Title", descKey: "landing.whyCard2Desc" },
  { key: "3", icon: Activity, iconBg: "bg-blue-500/15 text-blue-400", titleKey: "landing.whyCard3Title", descKey: "landing.whyCard3Desc" },
  { key: "4", icon: BarChart3, iconBg: "bg-[#F0B90B]/15 text-[#F0B90B]", titleKey: "landing.whyCard4Title", descKey: "landing.whyCard4Desc" },
  { key: "5", icon: TrendingUp, iconBg: "bg-emerald-500/15 text-emerald-400", titleKey: "landing.whyCard5Title", descKey: "landing.whyCard5Desc" },
  { key: "6", icon: Zap, iconBg: "bg-blue-500/15 text-blue-400", titleKey: "landing.whyCard6Title", descKey: "landing.whyCard6Desc" },
]

export default function LandingPage() {
  const t = useT()
  const params = useParams()
  const searchParams = useSearchParams()
  const locale = (params?.locale as string) || "en"
  const ref = (searchParams.get("ref") || "").trim()

  const handleGoogleSignIn = () => {
    if (typeof window !== "undefined" && ref) {
      localStorage.setItem(PENDING_REFERRAL_KEY, ref)
    }
    void signIn("google", { callbackUrl: "/dashboard" })
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <PublicLayoutHeader />

      {/* ── Hero ── */}
      <section className="relative overflow-hidden hero-mesh">
        {/* Subtle dot grid */}
        <div className="pointer-events-none absolute inset-0 opacity-[0.035]" style={{ backgroundImage: "radial-gradient(circle, #F0B90B 1px, transparent 1px)", backgroundSize: "40px 40px" }} />

        <div className="relative mx-auto max-w-6xl px-4 lg:px-8 py-20 lg:py-32 text-center">
          {/* Live badge */}
          <div className="inline-flex items-center gap-2 rounded-full yellow-badge px-4 py-1.5 text-xs font-bold mb-6 animate-hero-badge" style={{ animationDelay: "0.05s", animationFillMode: "backwards" }}>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#F0B90B] opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[#F0B90B]" />
            </span>
            {t("landing.moreProfitLessRisk")}
          </div>

          <h1 className="text-5xl lg:text-7xl font-black tracking-tight mb-6 animate-fade-in-up leading-[1.08]" style={{ animationDelay: "0.15s", animationFillMode: "backwards" }}>
            <span className="block text-primary">
              {t("landing.heroLine1")}
            </span>
            <span className="block text-foreground">
              {t("landing.heroLine2")}
            </span>
          </h1>

          <p className="text-lg lg:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 animate-fade-in-up" style={{ animationDelay: "0.25s", animationFillMode: "backwards" }}>
            {t("landing.heroSubtitleShort")}
          </p>

          <div className="flex flex-wrap items-center justify-center gap-4 mb-12 animate-fade-in-up" style={{ animationDelay: "0.35s", animationFillMode: "backwards" }}>
            <button
              type="button"
              onClick={handleGoogleSignIn}
              className="inline-flex items-center gap-2.5 rounded-lg px-7 py-3.5 text-base font-bold bg-primary text-primary-foreground hover:opacity-90 transition-opacity duration-150 active:scale-[0.97]"
            >
              <Zap className="h-5 w-5" />
              {t("login.signInWithGoogle")}
              <ArrowRight className="h-4 w-4" />
            </button>
            <div className="inline-flex items-center gap-2 rounded-xl border border-border bg-card/80 backdrop-blur-sm px-7 py-3.5 text-base font-semibold text-foreground hover:border-primary/40 hover:bg-primary/5 transition-all duration-200">
              <InstallAppButton variant="drawer" />
            </div>
          </div>

          {/* Trust badges */}
          <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-muted-foreground animate-fade-in" style={{ animationDelay: "0.45s", animationFillMode: "backwards" }}>
            {[
              { icon: Shield, label: t("landing.trustBadge1") },
              { icon: Lock, label: t("landing.trustBadge2") },
              { icon: CheckCircle2, label: t("landing.trustBadge3") },
            ].map(({ icon: Icon, label }) => (
              <span key={label} className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 backdrop-blur-sm px-3.5 py-1.5 text-xs">
                <Icon className="h-3.5 w-3.5 text-emerald" />
                {label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── Stats strip ── */}
      <section className="border-y border-border bg-card">
        <div className="mx-auto max-w-5xl px-4 py-10">
          <AnimateOnScroll stagger className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            {STATS.map(({ value, label }) => (
              <div key={label} className="space-y-1.5">
                <p className="stat-shimmer text-3xl lg:text-4xl font-black">{value}</p>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">{label}</p>
              </div>
            ))}
          </AnimateOnScroll>
        </div>
      </section>

      {/* ── What is lending ── */}
      <section className="px-4 lg:px-8 py-16 lg:py-20">
        <AnimateOnScroll>
          <div className="max-w-3xl mx-auto text-center">
            <p className="text-xs font-bold uppercase tracking-widest text-primary mb-3">How It Works</p>
            <h2 className="text-3xl lg:text-4xl font-black text-foreground mb-5 tracking-tight">{t("landing.whatIsLending")}</h2>
            <p className="text-muted-foreground text-base leading-relaxed mb-6">
              {t("landing.whatIsLendingBody")}
            </p>
            <Link href={`/${locale}/how-it-works`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline underline-offset-4 transition-opacity hover:opacity-80">
              {t("landing.learnMore")} <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </AnimateOnScroll>
      </section>

      {/* ── Strategy bot – 3 feature cards ── */}
      <section className="px-4 lg:px-8 py-16 lg:py-20 border-t border-border bg-muted/30">
        <div className="max-w-5xl mx-auto">
          <AnimateOnScroll>
            <p className="text-xs font-bold uppercase tracking-widest text-[#F0B90B] text-center mb-3">Strategy</p>
            <h2 className="text-3xl lg:text-4xl font-black text-foreground text-center mb-3 tracking-tight">{t("landing.strategyBotTitle")}</h2>
            <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">{t("landing.strategyBotSub")}</p>
          </AnimateOnScroll>
          <AnimateOnScroll stagger className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[
              { icon: Bot, titleKey: "landing.featureAutoTitle", descKey: "landing.featureAutoDesc", iconBg: "bg-[#F0B90B]/15 text-[#F0B90B]", accent: "hover:border-[#F0B90B]/30" },
              { icon: LineChart, titleKey: "landing.featureRatesTitle", descKey: "landing.featureRatesDesc", iconBg: "bg-[#0ECB81]/15 text-[#0ECB81]", accent: "hover:border-[#0ECB81]/30" },
              { icon: Settings2, titleKey: "landing.featureFollowTitle", descKey: "landing.featureFollowDesc", iconBg: "bg-blue-500/15 text-blue-400", accent: "hover:border-blue-500/30" },
            ].map(({ icon: Icon, titleKey, descKey, iconBg, accent }) => (
              <div key={titleKey} className={`group stat-card rounded-2xl p-7 text-center transition-all duration-300 ${accent} hover:-translate-y-1 hover:shadow-xl`}>
                <div className={`inline-flex h-14 w-14 items-center justify-center rounded-2xl ${iconBg} mb-5 mx-auto transition-transform duration-300 group-hover:scale-110`}>
                  <Icon className="h-6 w-6" />
                </div>
                <h3 className="font-bold text-foreground mb-2.5 text-base">{t(titleKey)}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{t(descKey)}</p>
              </div>
            ))}
          </AnimateOnScroll>
        </div>
      </section>

      {/* ── Why us – 6 cards ── */}
      <section className="px-4 lg:px-8 py-16 lg:py-20 border-t border-border">
        <AnimateOnScroll>
          <p className="text-xs font-bold uppercase tracking-widest text-[#F0B90B] text-center mb-3">Why Choose Us</p>
          <h2 className="text-3xl lg:text-4xl font-black text-foreground text-center mb-3 tracking-tight">{t("landing.strategyBotTitle")}</h2>
          <p className="text-center text-muted-foreground max-w-2xl mx-auto mb-12">
            {t("landing.whyUsTeaser")}
          </p>
        </AnimateOnScroll>
        <AnimateOnScroll stagger className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {WHY_CARDS.map(({ key, icon: Icon, iconBg, titleKey, descKey }) => (
            <div key={key} className="group stat-card rounded-2xl p-6 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg">
              <div className={`inline-flex h-10 w-10 items-center justify-center rounded-xl ${iconBg} mb-4 transition-transform duration-300 group-hover:scale-110`}>
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="font-bold text-foreground mb-1.5 text-sm">{t(titleKey)}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{t(descKey)}</p>
            </div>
          ))}
        </AnimateOnScroll>
        <AnimateOnScroll>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-6">
            <Link href={`/${locale}/strategy`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#F0B90B] hover:underline underline-offset-4">
              {t("pages.strategy")} <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Link href={`/${locale}/pricing`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#F0B90B] hover:underline underline-offset-4">
              {t("pages.pricing")} <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </AnimateOnScroll>
      </section>

      {/* ── Testimonials + Partners ── */}
      <AnimateOnScroll>
        <AaveStyleSection />
      </AnimateOnScroll>

      {/* ── Security ── */}
      <section className="px-4 lg:px-8 py-16 lg:py-20 border-t border-border bg-muted/30">
        <AnimateOnScroll>
          <div className="max-w-3xl mx-auto text-center">
            <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald/10 text-emerald mb-5 mx-auto">
              <Shield className="h-7 w-7" />
            </div>
            <h2 className="text-2xl font-black text-foreground mb-5">{t("landing.securityTitle")}</h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>{t("landing.securityFunds")}</p>
              <p>{t("landing.securityOAuth")} {t("landing.securityVault")}</p>
              <p className="text-xs opacity-60">{t("landing.securityRisk")}</p>
            </div>
          </div>
        </AnimateOnScroll>
      </section>

      {/* ── FAQ ── */}
      <section id="faq" className="px-4 lg:px-8 py-16 lg:py-20 border-t border-border scroll-mt-20">
        <AnimateOnScroll>
          <div className="max-w-2xl mx-auto">
            <p className="text-xs font-bold uppercase tracking-widest text-[#F0B90B] text-center mb-3">FAQ</p>
            <h2 className="text-2xl font-black text-foreground text-center mb-8">{t("landing.landingFaqTitle")}</h2>
            <Accordion type="single" collapsible className="w-full space-y-2">
              {FAQ_ITEMS.map((item, i) => (
                <AccordionItem key={item.q} value={`faq-${i}`} className="rounded-xl border border-border bg-card px-5 overflow-hidden data-[state=open]:border-primary/40">
                  <AccordionTrigger className="text-left font-semibold hover:no-underline hover:text-primary py-4 transition-colors">{t(item.q)}</AccordionTrigger>
                  <AccordionContent className="text-muted-foreground pb-4">{t(item.a)}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </AnimateOnScroll>
      </section>

      {/* ── Final CTA ── */}
      <section className="px-4 lg:px-8 py-20 lg:py-28 border-t border-border text-center relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 hero-mesh" />
        {/* Decorative dot grid */}
        <div className="pointer-events-none absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "radial-gradient(circle, #F0B90B 1px, transparent 1px)", backgroundSize: "40px 40px" }} />
        <AnimateOnScroll>
          <div className="relative">
            <p className="text-xs font-bold uppercase tracking-widest text-primary mb-4">{t("landing.moreProfitLessRisk")}</p>
            <h2 className="text-3xl lg:text-5xl font-black text-foreground mb-4 tracking-tight">
              {t("landing.ctaText")}
            </h2>
            <p className="text-sm text-muted-foreground mb-8 max-w-md mx-auto">{t("landing.aboutMission")}</p>
            <button
              type="button"
              onClick={handleGoogleSignIn}
              className="inline-flex items-center gap-2.5 rounded-lg px-8 py-4 text-base font-bold bg-primary text-primary-foreground hover:opacity-90 transition-opacity duration-150 active:scale-[0.97]"
            >
              <Zap className="h-5 w-5" />
              {t("login.signInWithGoogle")}
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </AnimateOnScroll>
      </section>

      <PublicLayoutFooter />
    </div>
  )
}
