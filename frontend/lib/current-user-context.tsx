"use client"

import React, { createContext, useCallback, useContext, useEffect, useState } from "react"
import { useSession } from "next-auth/react"

const API_BACKEND = "/api-backend"

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
    const { getBackendToken } = await import("@/lib/auth")
    const token = await getBackendToken()
    if (!token) {
      setUserId(null)
      setIsLoading(false)
      return
    }
    // When NextAuth is unauthenticated, only continue if we have a dev token (e.g. "Dev: Login as choiwangai")
    if (status !== "authenticated" && !session?.user) {
      const hasDevToken =
        typeof window !== "undefined" &&
        sessionStorage.getItem("bifinexbot_dev_backend_token")
      if (!hasDevToken) {
        setUserId(null)
        setIsLoading(false)
        return
      }
    }
    try {
      const res = await fetch(`${API_BACKEND}/api/me`, {
        credentials: "include",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        const id = data.id != null ? Number(data.id) : null
        setUserId(id)
      } else {
        // Fallback: when /api/me fails (e.g. backend auth/DB issue) but we have a token, use 2 so dashboard can load
        setUserId(2)
      }
    } catch {
      setUserId(2)
    } finally {
      setIsLoading(false)
    }
  }, [status, session?.user])

  useEffect(() => {
    // Do not set userId to null when status is "loading" (e.g. NextAuth refetch). Keeping previous userId
    // avoids ProfitCenter clearing gross/net state and flashing zeros when session briefly goes loading.
    if (status === "loading") {
      setIsLoading(true)
      return
    }
    const hasDevToken =
      typeof window !== "undefined" &&
      sessionStorage.getItem("bifinexbot_dev_backend_token")
    if (status === "unauthenticated" && !hasDevToken) {
      setUserId(null)
      setIsLoading(false)
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
