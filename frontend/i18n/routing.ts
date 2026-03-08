import { defineRouting } from "next-intl/routing"

/** Align with SUPPORTED_LOCALES in lib/i18n.tsx so language switcher and app locale stay in sync. */
export const routing = defineRouting({
  locales: ["en", "zh", "pt", "id", "ja", "ru", "de", "ko", "fil"],
  defaultLocale: "en",
})
