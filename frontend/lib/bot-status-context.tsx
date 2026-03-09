"use client"

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import { useSession, signIn } from "next-auth/react"
import { getBackendToken } from "@/lib/auth"
import { useCurrentUserId } from "@/lib/current-user-context"
import { useBotStats, useDashboardData } from "@/lib/dashboard-data-context"

import { API_BASE as API_BACKEND } from "@/lib/api-config"
const BOT_STATUS_POLL_MS = 90000
/** Cooldown (seconds) after Start or Stop before either can be clicked again. */
const BOT_ACTION_COOLDOWN_SEC = 5
/** Fast poll interval during transitional states (starting/stopping). */
const FAST_POLL_MS = 5_000

const INSUFFICIENT_TOKENS_MESSAGE = "Please add tokens to run the bot. A minimum balance of 1 token is required."

type BotStatusContextValue = {
  botActive: boolean | null
  /** Raw bot_status string from backend: "running" | "starting" | "stopping" | "stopped" */
  botStatus: string
  setBotActive: (v: boolean | null) => void
  loading: boolean
  isRevalidating: boolean
  error: string | null
  setError: (v: string | null) => void
  insufficientTokens: boolean
  isStarting: boolean
  isStopping: boolean
  actionCooldownSec: number
  refreshBotStatus: () => Promise<void>
  handleStart: () => Promise<void>
  handleStop: () => Promise<void>
  onUpgradeClick?: () => void
  /** Whether the user is signed in (NextAuth session or dev token) */
  isLoggedIn: boolean
  /** Whether the user has connected Bitfinex API keys */
  hasApiKeys: boolean
  /** When true, show the "connect API keys" popup */
  showApiKeysPopup: boolean
  setShowApiKeysPopup: (v: boolean) => void
  /** Navigate settings callback (set by parent) */
  onSettingsClick?: () => void
}

const BotStatusContext = createContext<BotStatusContextValue | null>(null)

type BotStatusProviderProps = { children: React.ReactNode; onUpgradeClick?: () => void; onSettingsClick?: () => void }

export function BotStatusProvider({ children, onUpgradeClick, onSettingsClick }: BotStatusProviderProps) {
  const { status: sessionStatus } = useSession()
  const hasDevToken = typeof window !== "undefined" && !!sessionStorage.getItem("bifinexbot_dev_backend_token")
  const isLoggedIn = sessionStatus === "authenticated" || hasDevToken

  const userId = useCurrentUserId()
  const id = userId ?? 0
  const botStats = useBotStats(id)
  const { getWallets, getLendingStats } = useDashboardData()
  const rawBotStatus = (botStats.data?.bot_status ?? "").toString().toLowerCase()
  const botActive =
    rawBotStatus === "running" || rawBotStatus === "starting"
      ? true
      : rawBotStatus === "stopped"
        ? false
        : (botStats.data?.active ?? null)
  const botStatus = rawBotStatus || "stopped"
  const hasApiKeys = botStats.data?.has_api_keys ?? false
  const [insufficientTokens, setInsufficientTokens] = useState(false)
  const [isStarting, setIsStarting] = useState(false)
  const startInProgressRef = useRef(false)
  const [isStopping, setIsStopping] = useState(false)
  const stopInProgressRef = useRef(false)
  const [actionCooldownSec, setActionCooldownSec] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [showApiKeysPopup, setShowApiKeysPopup] = useState(false)
  const loading = botStats.loading
  const isRevalidating = botStats.isRevalidating ?? false

  const refreshBotStatus = useCallback(() => botStats.refetch(), [botStats.refetch])

  // Poll only when tab is visible (Page Visibility API) to reduce server load from background tabs
  useEffect(() => {
    if (userId == null) return
    let intervalId: ReturnType<typeof setInterval> | null = null
    const startPolling = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return
      intervalId = setInterval(refreshBotStatus, BOT_STATUS_POLL_MS)
    }
    const stopPolling = () => {
      if (intervalId) {
        clearInterval(intervalId)
        intervalId = null
      }
    }
    startPolling()
    const onVisibility = () => {
      stopPolling()
      if (document.visibilityState === "visible") startPolling()
    }
    document.addEventListener("visibilitychange", onVisibility)
    return () => {
      document.removeEventListener("visibilitychange", onVisibility)
      stopPolling()
    }
  }, [userId, refreshBotStatus])

  // When status is "starting" or "stopping", poll more frequently to detect transitions
  useEffect(() => {
    if (userId == null) return
    if (rawBotStatus !== "starting" && rawBotStatus !== "stopping" && !isStarting && !isStopping) return
    const fastPollId = setInterval(refreshBotStatus, FAST_POLL_MS)
    return () => clearInterval(fastPollId)
  }, [userId, rawBotStatus, isStarting, isStopping, refreshBotStatus])

  // Clear local isStarting/isStopping once backend confirms a final state
  useEffect(() => {
    if (rawBotStatus === "running" || rawBotStatus === "stopped") {
      if (isStarting) setIsStarting(false)
      if (isStopping) setIsStopping(false)
    }
  }, [rawBotStatus, isStarting, isStopping])

  // Safety: force-clear transitional states after 30s to prevent stuck UI
  useEffect(() => {
    if (!isStarting && !isStopping) return
    const timeout = setTimeout(() => {
      setIsStarting(false)
      setIsStopping(false)
    }, 30_000)
    return () => clearTimeout(timeout)
  }, [isStarting, isStopping])

  // Tick down action cooldown every second
  useEffect(() => {
    if (actionCooldownSec <= 0) return
    const id = setInterval(() => {
      setActionCooldownSec((prev) => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(id)
  }, [actionCooldownSec])

  const handleStart = useCallback(async () => {
    if (!isLoggedIn) {
      void signIn("google", { callbackUrl: "/dashboard" })
      return
    }
    if (!hasApiKeys) {
      setShowApiKeysPopup(true)
      return
    }
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
      if (!res.ok) {
        setIsStarting(false)
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
        return
      }
      // Fire-and-forget background refresh; isStarting stays true until backend confirms "running"
      refreshBotStatus().catch(() => {})
      getWallets(id).refetch()
      getLendingStats(id).refetch()
    } catch (e) {
      setIsStarting(false)
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg === "Failed to fetch" || msg.includes("NetworkError") ? "API unreachable" : msg)
    } finally {
      startInProgressRef.current = false
    }
  }, [userId, refreshBotStatus, actionCooldownSec, getWallets, getLendingStats, id, isLoggedIn, hasApiKeys])

  const handleStop = useCallback(async () => {
    if (userId == null || actionCooldownSec > 0) return
    if (stopInProgressRef.current) return
    stopInProgressRef.current = true
    setActionCooldownSec(BOT_ACTION_COOLDOWN_SEC)
    try {
      setIsStopping(true)
      setError(null)
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/stop-bot`, { method: "POST", credentials: "include", headers })
      const text = await res.text()
      if (!res.ok) {
        setIsStopping(false)
        try {
          const j = text ? JSON.parse(text) : {}
          const detail = typeof j.detail === "string" ? j.detail : text
          setError(res.status === 429 ? (detail || "Too many start/stop requests. Please wait before trying again.") : (detail || "Stop failed"))
        } catch {
          setError(text || "Stop failed")
        }
        return
      }
      // Fire-and-forget background refresh; isStopping stays true until backend confirms "stopped"
      refreshBotStatus().catch(() => {})
      getWallets(id).refetch()
      getLendingStats(id).refetch()
    } catch (e) {
      setIsStopping(false)
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg === "Failed to fetch" || msg.includes("NetworkError") ? "API unreachable" : msg)
    } finally {
      stopInProgressRef.current = false
    }
  }, [userId, refreshBotStatus, actionCooldownSec, getWallets, getLendingStats, id])

  const value: BotStatusContextValue = {
    botActive,
    botStatus,
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
    isLoggedIn,
    hasApiKeys,
    showApiKeysPopup,
    setShowApiKeysPopup,
    onSettingsClick,
  }

  return <BotStatusContext.Provider value={value}>{children}</BotStatusContext.Provider>
}

export function useBotStatus() {
  const ctx = useContext(BotStatusContext)
  return ctx
}
