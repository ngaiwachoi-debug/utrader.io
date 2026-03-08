"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useParams, usePathname, useRouter } from "next/navigation"
import { signIn } from "next-auth/react"
import { useTheme } from "next-themes"
import { Sun, Moon, Menu, TrendingUp } from "lucide-react"
import { useT, useLanguage, SUPPORTED_LOCALES } from "@/lib/i18n"
import type { Lang } from "@/lib/i18n"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"

const LOCALE_LABELS: Record<string, string> = {
  en: "English", zh: "中文", pt: "Português", id: "Indonesia", ja: "日本語", ru: "Русский", de: "Deutsch", ko: "한국어", fil: "Filipino",
}

export function PublicLayoutHeader() {
  const t = useT()
  const params = useParams()
  const pathname = usePathname() ?? ""
  const router = useRouter()
  const { language, setLanguage } = useLanguage()
  const { setTheme, resolvedTheme } = useTheme()
  const [menuOpen, setMenuOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  const locale = (params?.locale as string) || "en"

  useEffect(() => setMounted(true), [])

  const isDark = mounted ? resolvedTheme === "dark" : false

  const localePattern = SUPPORTED_LOCALES.join("|")
  const pathWithoutLocale = pathname.replace(new RegExp(`^/(${localePattern})(?=/|$)`, "i"), "") || ""
  const homeHref = locale === "en" ? "/en" : `/${locale}`

  const handleLocaleChange = (value: string) => {
    const loc = value as Lang
    setLanguage(loc)
    const base = `/${loc}${pathWithoutLocale}`.replace(/\/$/, "") || `/${loc}`
    if (pathname !== base) router.push(base)
  }

  const navLinkClass =
    "rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent/10 transition-colors"
  const themeButtonClass =
    "rounded-lg p-2 text-muted-foreground hover:bg-accent/10 hover:text-foreground transition-colors flex items-center justify-center"

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur-xl">
      <div className="flex h-16 items-center justify-between px-4 lg:px-8 max-w-7xl mx-auto">
        {/* Logo */}
        <Link href={homeHref} className="flex items-center gap-2.5 group">
          <img 
            src="/logo.png" 
            alt="LendFinex logo" 
            className="h-8 w-8 shrink-0 object-contain logo-no-bg"
          />
          <span className="text-sm font-bold text-foreground group-hover:text-primary transition-colors">
            LendFinex
          </span>
        </Link>

        <div className="flex items-center gap-2 lg:gap-3">
          {/* Desktop nav links */}
          <nav className="hidden md:flex items-center gap-1">
            <Link href={`/${locale}/how-it-works`} className={navLinkClass}>
              {t("pages.howItWorks")}
            </Link>
            <Link href={`/${locale}/strategy`} className={navLinkClass}>
              {t("pages.strategy")}
            </Link>
            <Link href={`/${locale}/pricing`} className={navLinkClass}>
              {t("pages.pricing")}
            </Link>
          </nav>

          {/* Theme toggle */}
          <button
            type="button"
            onClick={() => setTheme(isDark ? "light" : "dark")}
            className={`hidden md:flex ${themeButtonClass}`}
            aria-label={isDark ? t("header.themeLight") : t("header.themeDark")}
            suppressHydrationWarning
          >
            {mounted ? (isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />) : <Sun className="h-4 w-4" />}
          </button>

          {/* Launch App CTA – Binance yellow */}
          <button
            type="button"
            onClick={() => void signIn("google", { callbackUrl: "/dashboard" })}
            className="hidden md:inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-bold bg-primary text-primary-foreground hover:opacity-90 transition-opacity duration-150"
          >
            Launch App
          </button>

          {/* Language picker */}
          <Select value={language} onValueChange={handleLocaleChange}>
            <SelectTrigger size="sm" className="flex w-[90px] sm:w-[100px] text-xs border-border bg-card">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SUPPORTED_LOCALES.map((loc) => (
                <SelectItem key={loc} value={loc}>{LOCALE_LABELS[loc] ?? loc}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Mobile hamburger */}
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                className="flex md:hidden rounded-lg p-2 text-muted-foreground hover:bg-accent/10 hover:text-foreground transition-colors"
                aria-label="Open menu"
              >
                <Menu className="h-5 w-5" />
              </button>
            </SheetTrigger>
            <SheetContent side="right" className="flex flex-col gap-4 pt-14 bg-card border-border">
              <nav className="flex flex-col gap-2">
                <Link href={`/${locale}/how-it-works`} className={navLinkClass} onClick={() => setMenuOpen(false)}>
                  {t("pages.howItWorks")}
                </Link>
                <Link href={`/${locale}/strategy`} className={navLinkClass} onClick={() => setMenuOpen(false)}>
                  {t("pages.strategy")}
                </Link>
                <Link href={`/${locale}/pricing`} className={navLinkClass} onClick={() => setMenuOpen(false)}>
                  {t("pages.pricing")}
                </Link>
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); void signIn("google", { callbackUrl: "/dashboard" }) }}
                  className="rounded-lg px-4 py-2.5 text-sm font-bold bg-primary text-primary-foreground hover:opacity-90 transition-opacity duration-150 text-left"
                >
                  Launch App
                </button>
              </nav>
              <div className="border-t border-border pt-4 flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Theme</span>
                  <button type="button" onClick={() => setTheme(isDark ? "light" : "dark")} className={themeButtonClass} aria-label={isDark ? t("header.themeLight") : t("header.themeDark")} suppressHydrationWarning>
                    {mounted ? (isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />) : <Sun className="h-4 w-4" />}
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Language</span>
                  <Select value={language} onValueChange={handleLocaleChange}>
                    <SelectTrigger size="sm" className="flex w-[90px] text-xs border-border bg-muted">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SUPPORTED_LOCALES.map((loc) => (
                        <SelectItem key={loc} value={loc}>{LOCALE_LABELS[loc] ?? loc}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  )
}

export function PublicLayoutFooter() {
  const t = useT()
  const params = useParams()
  const locale = (params?.locale as string) || "en"
  const homeHref = locale === "en" ? "/en" : `/${locale}`

  const footerLinks = [
    { label: t("pages.howItWorks"), href: `/${locale}/how-it-works` },
    { label: t("pages.strategy"), href: `/${locale}/strategy` },
    { label: t("pages.pricing"), href: `/${locale}/pricing` },
    { label: t("pages.faq"), href: `${homeHref}#faq` },
  ]
  const legalLinks = [
    { label: t("landing.footerLogin"), href: "/login" },
    { label: t("landing.footerDashboard"), href: "/dashboard" },
    { label: t("pages.terms"), href: `/${locale}/terms` },
    { label: t("pages.privacy"), href: `/${locale}/privacy` },
  ]

  return (
    <footer className="border-t border-border bg-muted/30">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-10">
          {/* Brand */}
          <div className="space-y-3">
            <Link href={homeHref} className="flex items-center gap-2">
              <img 
                src="/logo.png" 
                alt="LendFinex logo" 
                className="h-7 w-7 shrink-0 object-contain logo-no-bg"
              />
              <span className="text-sm font-bold text-foreground">
                LendFinex
              </span>
            </Link>
            <p className="text-xs text-muted-foreground max-w-[200px] leading-relaxed">
              AI-powered crypto lending automation for Bitfinex.
            </p>
          </div>
          {/* Product */}
          <div className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Product</p>
            <ul className="space-y-2">
              {footerLinks.map(({ label, href }) => (
                <li key={href}>
                  <Link href={href} className="text-xs text-muted-foreground hover:text-primary transition-colors">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          {/* Legal */}
          <div className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Legal</p>
            <ul className="space-y-2">
              {legalLinks.map(({ label, href }) => (
                <li key={href}>
                  <Link href={href} className="text-xs text-muted-foreground hover:text-primary transition-colors">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="border-t border-border pt-6 text-center">
          <p className="text-xs text-muted-foreground/70">
            {t("pages.footerDisclaimer")}
          </p>
        </div>
      </div>
    </footer>
  )
}
