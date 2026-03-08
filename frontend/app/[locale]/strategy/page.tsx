"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useT } from "@/lib/i18n"
import { PublicLayoutHeader, PublicLayoutFooter } from "@/components/landing/public-layout"
import { ArrowLeft, Radio, Filter, Layers, TrendingUp, Zap, BarChart3, Shield, Award, Cpu, LineChart, Bot, Check, X } from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export default function StrategyPage() {
  const t = useT()
  const params = useParams()
  const locale = (params?.locale as string) || "en"
  const homeHref = locale === "en" ? "/en" : `/${locale}`

  const flowSteps = [
    { key: "listen", icon: Radio, titleKey: "strategy.stepListen", descKey: "strategy.stepListenDesc" },
    { key: "filter", icon: Filter, titleKey: "strategy.stepFilter", descKey: "strategy.stepFilterDesc" },
    { key: "deploy", icon: Layers, titleKey: "strategy.stepDeploy", descKey: "strategy.stepDeployDesc" },
    { key: "earn", icon: TrendingUp, titleKey: "strategy.stepEarn", descKey: "strategy.stepEarnDesc" },
  ]

  const benefits = [
    { icon: TrendingUp, titleKey: "strategy.benefit1Title", descKey: "strategy.benefit1Desc" },
    { icon: Zap, titleKey: "strategy.benefit2Title", descKey: "strategy.benefit2Desc" },
    { icon: BarChart3, titleKey: "strategy.benefit3Title", descKey: "strategy.benefit3Desc" },
    { icon: Shield, titleKey: "strategy.benefit4Title", descKey: "strategy.benefit4Desc" },
  ]

  const comparisons = [
    { nameKey: "strategy.compareManual", descKey: "strategy.compareManualDesc", us: false },
    { nameKey: "strategy.compareSimpleBot", descKey: "strategy.compareSimpleBotDesc", us: false },
    { nameKey: "strategy.compareExchange", descKey: "strategy.compareExchangeDesc", us: false },
    { nameKey: "strategy.compareUs", descKey: "strategy.compareUsDesc", us: true },
  ]

  const standOut = [
    { icon: Layers, titleKey: "strategy.standOut1Title", descKey: "strategy.standOut1Desc" },
    { icon: LineChart, titleKey: "strategy.standOut2Title", descKey: "strategy.standOut2Desc" },
    { icon: Cpu, titleKey: "strategy.standOut3Title", descKey: "strategy.standOut3Desc" },
    { icon: Shield, titleKey: "strategy.standOut4Title", descKey: "strategy.standOut4Desc" },
  ]

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <PublicLayoutHeader />
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-10">
        <Link
          href={homeHref}
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          {t("pages.backToHome")}
        </Link>
        <h1 className="text-2xl font-bold text-foreground mb-2">{t("strategy.title")}</h1>
        <p className="text-muted-foreground mb-12">{t("strategy.subtitle")}</p>

        {/* How it functions */}
        <section className="mb-14">
          <h2 className="text-xl font-bold text-foreground mb-2">{t("strategy.howItFunctionsTitle")}</h2>
          <p className="text-muted-foreground mb-8">{t("strategy.howItFunctionsIntro")}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {flowSteps.map(({ key, icon: Icon, titleKey, descKey }) => (
              <div key={key} className="rounded-xl border border-border bg-card p-5">
                <div className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary mb-3">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="font-semibold text-foreground mb-1">{t(titleKey)}</h3>
                <p className="text-sm text-muted-foreground">{t(descKey)}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Strategy components (tabs) */}
        <section className="mb-14">
          <h2 className="text-xl font-bold text-foreground mb-2">{t("strategy.componentsTitle")}</h2>
          <p className="text-muted-foreground mb-6">{t("strategy.componentsIntro")}</p>
          <Tabs defaultValue="predator" className="w-full">
            <TabsList className="grid w-full grid-cols-2 sm:grid-cols-4 mb-6">
              <TabsTrigger value="predator" className="text-xs sm:text-sm">{t("strategy.tabPredator")}</TabsTrigger>
              <TabsTrigger value="gemini" className="text-xs sm:text-sm">{t("strategy.tabGemini")}</TabsTrigger>
              <TabsTrigger value="momentum" className="text-xs sm:text-sm">{t("strategy.tabMomentum")}</TabsTrigger>
              <TabsTrigger value="listener" className="text-xs sm:text-sm">{t("strategy.tabListener")}</TabsTrigger>
            </TabsList>
            <TabsContent value="predator" className="space-y-4 text-muted-foreground">
              <h3 className="text-lg font-semibold text-foreground">{t("strategy.predatorTitle")}</h3>
              <p>{t("strategy.predatorBody")}</p>
            </TabsContent>
            <TabsContent value="gemini" className="space-y-4 text-muted-foreground">
              <h3 className="text-lg font-semibold text-foreground">{t("strategy.geminiTitle")}</h3>
              <p>{t("strategy.geminiBody")}</p>
            </TabsContent>
            <TabsContent value="momentum" className="space-y-4 text-muted-foreground">
              <h3 className="text-lg font-semibold text-foreground">{t("strategy.momentumTitle")}</h3>
              <p>{t("strategy.momentumBody")}</p>
            </TabsContent>
            <TabsContent value="listener" className="space-y-4 text-muted-foreground">
              <h3 className="text-lg font-semibold text-foreground">{t("strategy.listenerTitle")}</h3>
              <p>{t("strategy.listenerBody")}</p>
            </TabsContent>
          </Tabs>
        </section>

        {/* Why it benefits you */}
        <section className="mb-14 rounded-xl border border-border bg-muted/20 p-6 lg:p-8">
          <h2 className="text-xl font-bold text-foreground mb-2">{t("strategy.whyBenefitsTitle")}</h2>
          <p className="text-muted-foreground mb-8">{t("strategy.whyBenefitsIntro")}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {benefits.map(({ icon: Icon, titleKey, descKey }) => (
              <div key={titleKey} className="flex gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground mb-1">{t(titleKey)}</h3>
                  <p className="text-sm text-muted-foreground">{t(descKey)}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Compared to the market */}
        <section className="mb-14">
          <h2 className="text-xl font-bold text-foreground mb-2">{t("strategy.compareTitle")}</h2>
          <p className="text-muted-foreground mb-6">{t("strategy.compareIntro")}</p>
          <div className="space-y-4">
            {comparisons.map(({ nameKey, descKey, us }) => (
              <div
                key={nameKey}
                className={`rounded-xl border p-5 ${us ? "border-primary bg-primary/5" : "border-border bg-card"}`}
              >
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${us ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>
                    {us ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
                  </div>
                  <div>
                    <h3 className={`font-semibold ${us ? "text-primary" : "text-foreground"}`}>{t(nameKey)}</h3>
                    <p className="text-sm text-muted-foreground mt-1">{t(descKey)}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Why we stand out */}
        <section className="mb-14 rounded-xl border border-border bg-card p-6 lg:p-8">
          <h2 className="text-xl font-bold text-foreground mb-2 flex items-center gap-2">
            <Award className="h-5 w-5 text-primary" />
            {t("strategy.whyStandOutTitle")}
          </h2>
          <p className="text-muted-foreground mb-8">{t("strategy.whyStandOutIntro")}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {standOut.map(({ icon: Icon, titleKey, descKey }) => (
              <div key={titleKey} className="flex gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground mb-1">{t(titleKey)}</h3>
                  <p className="text-sm text-muted-foreground">{t(descKey)}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="text-center">
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Bot className="h-4 w-4" />
            {t("landing.startFreeTrial")}
          </Link>
        </div>
      </main>
      <PublicLayoutFooter />
    </div>
  )
}
