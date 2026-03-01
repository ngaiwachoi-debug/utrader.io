"use client"

import React, { createContext, useCallback, useContext, useEffect, useState } from "react"
import { getBackendToken } from "@/lib/auth"
import { useCurrentUserId } from "@/lib/current-user-context"

const API_BACKEND = "/api-backend"
const BOT_STATUS_POLL_MS = 90000
/** Cooldown (seconds) after Start or Stop before either can be clicked again. */
const BOT_ACTION_COOLDOWN_SEC = 10

const INSUFFICIENT_TOKENS_MESSAGE = "Please add tokens to run the bot. A minimum balance of 1 token is required."

type BotStatusContextValue = {
  botActive: boolean | null
  setBotActive: (v: boolean | null) => void
  loading: boolean
  error: string | null
  setError: (v: string | null) => void
  /** True when Start returned 400 with INSUFFICIENT_TOKENS; show message + button to Subscription tab */
  insufficientTokens: boolean
  isStarting: boolean
  isStopping: boolean
  /** Seconds remaining in the 10s cooldown after Start/Stop (0 = no cooldown) */
  actionCooldownSec: number
  refreshBotStatus: () => Promise<void>
  handleStart: () => Promise<void>
  handleStop: () => Promise<void>
  /** Callback to switch to Subscription tab (e.g. setActivePage("subscription")) */
  onUpgradeClick?: () => void
}

const BotStatusContext = createContext<BotStatusContextValue | null>(null)

type BotStatusProviderProps = { children: React.ReactNode; onUpgradeClick?: () => void }

export function BotStatusProvider({ children, onUpgradeClick }: BotStatusProviderProps) {
  const userId = useCurrentUserId()
  const [botActive, setBotActive] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [insufficientTokens, setInsufficientTokens] = useState(false)
  const [isStarting, setIsStarting] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [actionCooldownSec, setActionCooldownSec] = useState(0)

  const refreshBotStatus = useCallback(async () => {
    if (userId == null) return
    const token = await getBackendToken()
    const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
    const res = await fetch(`${API_BACKEND}/bot-stats/${userId}`, { credentials: "include", headers })
    if (res.ok) {
      const data = await res.json()
      if (typeof data.active === "boolean") setBotActive(data.active)
    }
  }, [userId])

  useEffect(() => {
    if (userId == null) {
      setBotActive(null)
      return
    }
    refreshBotStatus()
    const t = setInterval(refreshBotStatus, BOT_STATUS_POLL_MS)
    return () => clearInterval(t)
  }, [userId, refreshBotStatus])

  // Tick down action cooldown every second
  useEffect(() => {
    if (actionCooldownSec <= 0) return
    const id = setInterval(() => {
      setActionCooldownSec((prev) => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(id)
  }, [actionCooldownSec])

  const handleStart = useCallback(async () => {
    if (userId == null || actionCooldownSec > 0) return
    setActionCooldownSec(BOT_ACTION_COOLDOWN_SEC)
    try {
      setIsStarting(true)
      setError(null)
      setInsufficientTokens(false)
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/start-bot`, { method: "POST", credentials: "include", headers })
      const text = await res.text()
      const data = res.ok ? (text ? JSON.parse(text) : {}) : null
      if (!res.ok) {
        try {
          const j = text ? JSON.parse(text) : {}
          const detail = typeof j.detail === "string" ? j.detail : ""
          const isInsufficient = j.code === "INSUFFICIENT_TOKENS" || (detail && String(detail).toLowerCase().includes("minimum balance"))
          setError(isInsufficient ? INSUFFICIENT_TOKENS_MESSAGE : (detail || text || "Start failed"))
          setInsufficientTokens(!!isInsufficient)
        } catch {
          setError(text || "Start failed")
        }
      } else if (data && (data.bot_status === "running" || data.bot_status === "starting")) {
        setBotActive(true)
      } else {
        await refreshBotStatus()
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg === "Failed to fetch" || msg.includes("NetworkError") ? "API unreachable" : msg)
    } finally {
      setIsStarting(false)
    }
  }, [userId, refreshBotStatus, actionCooldownSec])

  const handleStop = useCallback(async () => {
    if (userId == null || actionCooldownSec > 0) return
    setActionCooldownSec(BOT_ACTION_COOLDOWN_SEC)
    try {
      setIsStopping(true)
      setError(null)
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/stop-bot`, { method: "POST", credentials: "include", headers })
      if (!res.ok) {
        const text = await res.text()
        try {
          const j = JSON.parse(text)
          setError(j.detail || text)
        } catch {
          setError(text || "Stop failed")
        }
      } else {
        setBotActive(false)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg === "Failed to fetch" || msg.includes("NetworkError") ? "API unreachable" : msg)
    } finally {
      setIsStopping(false)
    }
  }, [userId, actionCooldownSec])

  const value: BotStatusContextValue = {
    botActive,
    setBotActive,
    loading,
    error,
    setError,
    insufficientTokens,
    isStarting,
    isStopping,
    actionCooldownSec,
    refreshBotStatus,
    handleStart,
    handleStop,
    onUpgradeClick,
  }

  return <BotStatusContext.Provider value={value}>{children}</BotStatusContext.Provider>
}

export function useBotStatus() {
  const ctx = useContext(BotStatusContext)
  return ctx
}
