import { defineRouting } from "next-intl/routing"

export const routing = defineRouting({
  locales: ["en", "zh", "ko", "ru", "de"],
  defaultLocale: "en",
})
