"use client"

import { useState, useEffect, useRef } from "react"
import { Download } from "lucide-react"
import { useT } from "@/lib/i18n"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

/** BeforeInstallPromptEvent is not in TypeScript DOM lib; Chrome fires it when PWA is installable. */
type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
}

type InstallAppButtonProps = { variant?: "header" | "drawer" }

const buttonBase = "flex items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
const headerClass = "hidden sm:flex items-center gap-1.5 p-2"
const drawerClass = "flex w-full items-center gap-3 text-sm font-medium"

export function InstallAppButton({ variant = "header" }: InstallAppButtonProps) {
  const t = useT()
  const [installAvailable, setInstallAvailable] = useState(false)
  const [showFallback, setShowFallback] = useState(false)
  const [installed, setInstalled] = useState(false)
  const deferredPrompt = useRef<BeforeInstallPromptEvent | null>(null)
  const isDrawer = variant === "drawer"
  const buttonClass = isDrawer ? `${buttonBase} ${drawerClass}` : `${buttonBase} ${headerClass}`

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault()
      deferredPrompt.current = e as BeforeInstallPromptEvent
      setInstallAvailable(true)
    }
    window.addEventListener("beforeinstallprompt", handler)
    return () => {
      window.removeEventListener("beforeinstallprompt", handler)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    const standalone = window.matchMedia("(display-mode: standalone)").matches
    const isStandalone = (navigator as { standalone?: boolean }).standalone === true
    if (standalone || isStandalone) setInstalled(true)
  }, [])

  const handleInstall = async () => {
    const prompt = deferredPrompt.current
    if (prompt) {
      await prompt.prompt()
      const { outcome } = await prompt.userChoice
      if (outcome === "accepted") {
        setInstallAvailable(false)
        setInstalled(true)
      }
      deferredPrompt.current = null
    }
  }

  if (installed) return null

  if (installAvailable) {
    return (
      <button
        type="button"
        onClick={handleInstall}
        className={buttonClass}
        aria-label={t("header.installApp")}
        title={t("header.installAppTitle")}
      >
        <Download className="h-4 w-4 shrink-0" />
        {isDrawer && <span>{t("header.installApp")}</span>}
      </button>
    )
  }

  const fallbackTrigger = (
    <button
      type="button"
      className={buttonClass}
      aria-label={t("header.installApp")}
      title={t("header.installAppTitle")}
      aria-haspopup="dialog"
      aria-expanded={showFallback}
    >
      <Download className="h-4 w-4 shrink-0" />
      {isDrawer && <span>{t("header.installApp")}</span>}
    </button>
  )

  return (
    <Popover open={showFallback} onOpenChange={setShowFallback}>
      <PopoverTrigger asChild>{fallbackTrigger}</PopoverTrigger>
      <PopoverContent className="w-72 text-sm" align={isDrawer ? "center" : "end"}>
        <p className="font-medium text-foreground mb-2">{t("header.installAppShortcut")}</p>
        <p className="text-muted-foreground text-xs mb-2">{t("header.installAppChromeHint")}</p>
        <p className="text-muted-foreground text-xs">
          {t("header.installAppChromeSteps")}
        </p>
      </PopoverContent>
    </Popover>
  )
}
