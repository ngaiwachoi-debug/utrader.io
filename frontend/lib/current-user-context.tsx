"use client"

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"

type CurrentUserContextValue = {
  userId: number | null
  isLoading: boolean
  apiError: boolean
  refetch: () => void
}

const CurrentUserContext = createContext<CurrentUserContextValue | null>(null)

export function CurrentUserProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession()
  const [userId, setUserId] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [apiError, setApiError] = useState(false)
  const lastUserIdRef = useRef<number | null>(null)

  const fetchMe = useCallback(async () => {
    if (status !== "authenticated" || !session?.user) {
      setUserId(null)
      lastUserIdRef.current = null
      setApiError(false)
      setIsLoading(false)
      return
    }
    setApiError(false)
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
        const id = data.id != null ? Number(data.id) : null
        setUserId(id)
        lastUserIdRef.current = id
      } else if (res.status === 401) {
        setUserId(null)
        lastUserIdRef.current = null
      } else {
        setApiError(true)
        setUserId(lastUserIdRef.current)
      }
    } catch {
      setApiError(true)
      setUserId(lastUserIdRef.current)
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
    apiError,
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
  return ctx ?? { userId: null, isLoading: true, apiError: false, refetch: () => {} }
}
