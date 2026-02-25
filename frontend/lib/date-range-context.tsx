"use client"

import React, { createContext, useCallback, useContext, useState } from "react"
import { addDays, format, startOfDay, subDays } from "date-fns"

export type DateRange = { start: Date; end: Date }

const defaultEnd = new Date(2026, 1, 25) // Feb 25, 2026
const defaultStart = subDays(defaultEnd, 30)

const DateRangeContext = createContext<{
  range: DateRange
  setRange: (range: DateRange) => void
  formatRange: () => string
} | null>(null)

export function DateRangeProvider({ children }: { children: React.ReactNode }) {
  const [range, setRangeState] = useState<DateRange>({
    start: startOfDay(defaultStart),
    end: startOfDay(defaultEnd),
  })

  const setRange = useCallback((r: DateRange) => {
    setRangeState({ start: startOfDay(r.start), end: startOfDay(r.end) })
  }, [])

  const formatRange = useCallback(() => {
    return `${format(range.start, "MMM d, yyyy")} - ${format(range.end, "MMM d, yyyy")}`
  }, [range])

  return (
    <DateRangeContext.Provider value={{ range, setRange, formatRange }}>
      {children}
    </DateRangeContext.Provider>
  )
}

export function useDateRange() {
  const ctx = useContext(DateRangeContext)
  if (!ctx) {
    const fallback = { start: defaultStart, end: defaultEnd }
    return {
      range: fallback,
      setRange: () => {},
      formatRange: () => `${format(defaultStart, "MMM d, yyyy")} - ${format(defaultEnd, "MMM d, yyyy")}`,
    }
  }
  return ctx
}

export { addDays, subDays, format, startOfDay }
