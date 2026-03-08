"use client"

import { useState, useEffect, useCallback } from "react"
import { useT } from "@/lib/i18n"

const CAROUSEL_QUOTES = [
  { quoteKey: "landing.carouselQuote1", authorKey: "landing.carouselAuthor1" },
  { quoteKey: "landing.carouselQuote2", authorKey: "landing.carouselAuthor2" },
  { quoteKey: "landing.carouselQuote3", authorKey: "landing.carouselAuthor3" },
  { quoteKey: "landing.carouselQuote4", authorKey: "landing.carouselAuthor4" },
  { quoteKey: "landing.carouselQuote5", authorKey: "landing.carouselAuthor5" },
] as const

const PARTNERS = [
  { name: "Bitfinex", src: "/partners/bitfinex.png" },
  { name: "Aave", src: "/partners/aave.png" },
  { name: "Banco Central do Brasil", src: "/partners/banco-central.png" },
  { name: "Centrifuge", src: "/partners/centrifuge.png" },
  { name: "Galaxy", src: "/partners/galaxy.png" },
  { name: "Fireblocks", src: "/partners/fireblocks.png" },
  { name: "Consensys", src: "/partners/consensys.png" },
]

function PartnerLogo({ name, src }: { name: string; src: string }) {
  const [failed, setFailed] = useState(false)
  return (
    <div className="flex-shrink-0 mx-10 flex items-center justify-center h-12 min-w-[140px]">
      {!failed ? (
        <img
          src={src}
          alt={name}
          className="h-8 w-auto max-w-[140px] object-contain object-center opacity-60 hover:opacity-100 transition-opacity dark:brightness-0 dark:invert"
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="text-muted-foreground text-xs font-medium whitespace-nowrap">{name}</span>
      )}
    </div>
  )
}

export function AaveStyleSection() {
  const t = useT()
  const [activeIndex, setActiveIndex] = useState(0)

  const goTo = useCallback((index: number) => {
    setActiveIndex((index + CAROUSEL_QUOTES.length) % CAROUSEL_QUOTES.length)
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      setActiveIndex((i) => (i + 1) % CAROUSEL_QUOTES.length)
    }, 5000)
    return () => clearInterval(id)
  }, [])

  return (
    <section className="border-t border-border overflow-hidden">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 py-16 lg:py-24">
        <p className="text-xs font-bold uppercase tracking-widest text-primary mb-4">Community</p>
        <h2 className="text-3xl lg:text-5xl font-black text-foreground mb-5 tracking-tight max-w-xl leading-tight">
          {t("landing.bestBuildTitle")}
        </h2>
        <p className="text-muted-foreground max-w-lg text-base leading-relaxed">
          {t("landing.bestBuildSub")}
        </p>
      </div>

      <div className="px-4 lg:px-8 py-12 lg:py-16 border-t border-border bg-muted/30">
        <div className="max-w-4xl mx-auto">
          <div className="relative overflow-hidden">
            <div
              className="flex transition-transform duration-500 ease-out"
              style={{ width: `${CAROUSEL_QUOTES.length * 100}%`, transform: `translateX(-${activeIndex * (100 / CAROUSEL_QUOTES.length)}%)` }}
            >
              {CAROUSEL_QUOTES.map(({ quoteKey, authorKey }, index) => (
                <div
                  key={quoteKey}
                  className="flex-shrink-0 px-4 md:px-8"
                  style={{ width: `${100 / CAROUSEL_QUOTES.length}%` }}
                >
                  <div
                    className={`mx-auto max-w-2xl rounded-2xl border p-8 transition-all duration-300 ${
                      index === activeIndex
                        ? "border-primary/30 bg-primary/5 opacity-100 scale-100 shadow-lg shadow-primary/5"
                        : "border-border bg-card opacity-30 scale-95"
                    }`}
                  >
                    <div className="mb-4 text-primary/40 text-4xl leading-none">&ldquo;</div>
                    <p className="text-foreground text-sm md:text-base leading-relaxed font-medium">
                      {t(quoteKey)}
                    </p>
                    <p className="mt-6 text-xs font-bold uppercase tracking-widest text-muted-foreground">{t(authorKey)}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-center gap-2 mt-8">
              {CAROUSEL_QUOTES.map((_, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => goTo(index)}
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    index === activeIndex ? "w-8 bg-primary" : "w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/50"
                  }`}
                  aria-label={`Go to testimonial ${index + 1}`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-border py-10 lg:py-14 bg-card">
        <div className="relative overflow-hidden w-full">
          <div className="pointer-events-none absolute left-0 top-0 h-full w-20 z-10 bg-gradient-to-r from-card to-transparent" />
          <div className="pointer-events-none absolute right-0 top-0 h-full w-20 z-10 bg-gradient-to-l from-card to-transparent" />
          <div className="flex w-max animate-[scroll_40s_linear_infinite] hover:[animation-play-state:paused]">
            {[...PARTNERS, ...PARTNERS].map((partner, i) => (
              <PartnerLogo key={`${partner.name}-${i}`} name={partner.name} src={partner.src} />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}