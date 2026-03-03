"use client"

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import { getBackendToken } from "@/lib/auth"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useBotStats } from "@/lib/dashboard-data-context"

const API_BACKEND = "/api-backend"
const BOT_STATUS_POLL_MS = 90000
/** Cooldown (seconds) after Start or Stop before either can be clicked again. */
const BOT_ACTION_COOLDOWN_SEC = 10

const INSUFFICIENT_TOKENS_MESSAGE = "Please add tokens to run the bot. A minimum balance of 1 token is required."

type BotStatusContextValue = {
  botActive: boolean | null
  setBotActive: (v: boolean | null) => void
  loading: boolean
  /** True when refetching in background (cached data shown but status may change) */
  isRevalidating: boolean
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
  const id = userId ?? 0
  const botStats = useBotStats(id)
  const botActive = botStats.data?.active ?? null
  const [insufficientTokens, setInsufficientTokens] = useState(false)
  const [isStarting, setIsStarting] = useState(false)
  const startInProgressRef = useRef(false)
  const [isStopping, setIsStopping] = useState(false)
  const stopInProgressRef = useRef(false)
  const [actionCooldownSec, setActionCooldownSec] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const loading = botStats.loading
  const isRevalidating = botStats.isRevalidating ?? false

  const refreshBotStatus = useCallback(() => botStats.refetch(), [botStats.refetch])

  useEffect(() => {
    if (userId == null) return
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
    if (startInProgressRef.current) return
    startInProgressRef.current = true
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
          if (res.status === 429) {
            setError(detail || "Too many start/stop requests. Please wait before trying again.")
          } else {
            const isInsufficient = j.code === "INSUFFICIENT_TOKENS" || (detail && String(detail).toLowerCase().includes("minimum balance"))
            setError(isInsufficient ? INSUFFICIENT_TOKENS_MESSAGE : (detail || text || "Start failed"))
            setInsufficientTokens(!!isInsufficient)
          }
        } catch {
          setError(text || "Start failed")
        }
      } else if (data && (data.bot_status === "running" || data.bot_status === "starting")) {
        await refreshBotStatus()
      } else {
        await refreshBotStatus()
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg === "Failed to fetch" || msg.includes("NetworkError") ? "API unreachable" : msg)
    } finally {
      startInProgressRef.current = false
      setIsStarting(false)
    }
  }, [userId, refreshBotStatus, actionCooldownSec])

  const handleStop = useCallback(async () => {
    if (userId == null || actionCooldownSec > 0) return
    if (stopInProgressRef.current) return
    stopInProgressRef.current = true
    const log = (msg: string, data?: object) => {
      try {
        console.log("[stop-bot]", msg, data ?? "")
      } catch {
        // no-op
      }
    }
    setActionCooldownSec(BOT_ACTION_COOLDOWN_SEC)
    try {
      setIsStopping(true)
      setError(null)
      log("handleStop called", { userId })
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      log("POST /stop-bot sending")
      const res = await fetch(`${API_BACKEND}/stop-bot`, { method: "POST", credentials: "include", headers })
      const text = await res.text()
      log("POST /stop-bot response", { status: res.status, ok: res.ok, bodyLength: text?.length })
      if (!res.ok) {
        try {
          const j = text ? JSON.parse(text) : {}
          const detail = typeof j.detail === "string" ? j.detail : text
          log("stop-bot error response", { status: res.status, detail: detail || text })
          setError(res.status === 429 ? (detail || "Too many start/stop requests. Please wait before trying again.") : (detail || "Stop failed"))
        } catch {
          log("stop-bot error body parse failed", { text: text?.slice(0, 200) })
          setError(text || "Stop failed")
        }
      } else {
        try {
          const data = text ? JSON.parse(text) : {}
          log("stop-bot success", data)
        } catch {
          log("stop-bot success body", { raw: text?.slice(0, 200) })
        }
        await refreshBotStatus()
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      log("stop-bot exception", { message: msg, name: e instanceof Error ? e.name : undefined })
      setError(msg === "Failed to fetch" || msg.includes("NetworkError") ? "API unreachable" : msg)
    } finally {
      stopInProgressRef.current = false
      setIsStopping(false)
    }
  }, [userId, refreshBotStatus, actionCooldownSec])

  const value: BotStatusContextValue = {
    botActive,
    setBotActive: () => { void refreshBotStatus() },
    loading,
    isRevalidating,
    error: error ?? botStats.error,
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
