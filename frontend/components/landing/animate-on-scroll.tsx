"use client"

import { useRef, useEffect, useState } from "react"

type Props = {
  children: React.ReactNode
  className?: string
  /** Optional: root margin so animation triggers a bit before fully in view (e.g. "0px 0px -80px 0px") */
  rootMargin?: string
  /** If true, children get stagger class so only direct children need landing-animate-init */
  stagger?: boolean
}

export function AnimateOnScroll({ children, className = "", rootMargin = "0px 0px -60px 0px", stagger = false }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) setVisible(true)
      },
      { threshold: 0.1, rootMargin }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [rootMargin])

  return (
    <div
      ref={ref}
      className={`${visible ? "landing-animate-visible" : "landing-animate-init"} ${stagger ? "landing-stagger" : ""} ${className}`}
    >
      {children}
    </div>
  )
}
