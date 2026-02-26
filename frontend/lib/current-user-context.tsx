"use client"

import React, { createContext, useCallback, useContext, useEffect, useState } from "react"
import { useSession } from "next-auth/react"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type CurrentUserContextValue = {
  userId: number | null
  isLoading: boolean
  refetch: () => void
}

const CurrentUserContext = createContext<CurrentUserContextValue | null>(null)

export function CurrentUserProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession()
  const [userId, setUserId] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchMe = useCallback(async () => {
    if (status !== "authenticated" || !session?.user) {
      setUserId(null)
      setIsLoading(false)
      return
    }
    try {
      const { getBackendToken } = await import("@/lib/auth")
      const token = await getBackendToken()
      if (!token) {
        setUserId(null)
        setIsLoading(false)
        return
      }
      const res = await fetch(`${API_BASE}/api/me`, {
        credentials: "include",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setUserId(data.id != null ? Number(data.id) : null)
      } else {
        setUserId(null)
      }
    } catch {
      setUserId(null)
    } finally {
      setIsLoading(false)
    }
  }, [status, session?.user])

  useEffect(() => {
    if (status === "unauthenticated" || status === "loading") {
      setUserId(null)
      setIsLoading(status === "loading")
      return
    }
    fetchMe()
  }, [status, session?.user, fetchMe])

  const value: CurrentUserContextValue = {
    userId,
    isLoading,
    refetch: fetchMe,
  }

  return (
    <CurrentUserContext.Provider value={value}>
      {children}
    </CurrentUserContext.Provider>
  )
}

export function useCurrentUserId(): number | null {
  const ctx = useContext(CurrentUserContext)
  return ctx?.userId ?? null
}

export function useCurrentUser(): CurrentUserContextValue {
  const ctx = useContext(CurrentUserContext)
  return ctx ?? { userId: null, isLoading: true, refetch: () => {} }
}
