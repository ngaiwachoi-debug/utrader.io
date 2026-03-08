"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useT } from "@/lib/i18n"
import { PublicLayoutHeader, PublicLayoutFooter } from "@/components/landing/public-layout"
import { ArrowLeft } from "lucide-react"

export default function TermsPage() {
  const t = useT()
  const params = useParams()
  const locale = (params?.locale as string) || "en"

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <PublicLayoutHeader />
      <main className="flex-1 max-w-3xl mx-auto w-full px-4 py-10">
        <Link
          href={locale === "en" ? "/en" : `/${locale}`}
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          {t("pages.backToHome")}
        </Link>
        <h1 className="text-2xl font-bold text-foreground mb-2">{t("terms.title")}</h1>
        <p className="text-sm text-muted-foreground mb-8">{t("terms.lastUpdated")}: March 2025</p>
        <div className="prose prose-sm dark:prose-invert max-w-none space-y-6 text-muted-foreground">
          <p>{t("terms.intro")}</p>
          <section>
            <h2 className="text-lg font-semibold text-foreground mt-8 mb-2">{t("terms.section1Title")}</h2>
            <p>{t("terms.section1Body")}</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-foreground mt-8 mb-2">{t("terms.section2Title")}</h2>
            <p>{t("terms.section2Body")}</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-foreground mt-8 mb-2">{t("terms.section3Title")}</h2>
            <p>{t("terms.section3Body")}</p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-foreground mt-8 mb-2">{t("terms.section4Title")}</h2>
            <p>{t("terms.section4Body")}</p>
          </section>
        </div>
      </main>
      <PublicLayoutFooter />
    </div>
  )
}
