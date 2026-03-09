"use client"

import { useRef, useState, useEffect, useCallback } from "react"
import { RefreshCw, Play, Square, Loader2, KeyRound, X } from "lucide-react"
import { useT } from "@/lib/i18n"
import { useBotStatus } from "@/lib/bot-status-context"

const REFRESH_MIN_INTERVAL_MS = 10_000

type BotStatusBarProps = {
  title?: string
  date?: string
  onRefresh?: () => void
  refreshCooldownSec?: number
}

export function BotStatusBar({ title, date, onRefresh, refreshCooldownSec = 0 }: BotStatusBarProps) {
  const t = useT()
  const ctx = useBotStatus()
  const lastRefreshRef = useRef(0)
  const [refreshSpinning, setRefreshSpinning] = useState(false)

  if (!ctx) return null

  const {
    botActive, botStatus, loading, isRevalidating,
    error, setError, insufficientTokens,
    isStarting, isStopping, actionCooldownSec: ctxCooldown,
    refreshBotStatus, handleStart, handleStop,
    onUpgradeClick, isLoggedIn, hasApiKeys,
    showApiKeysPopup, setShowApiKeysPopup, onSettingsClick,
  } = ctx

  const statusLoading = loading || isRevalidating
  const statusUnknown = botActive === null

  const isStartingState = botStatus === "starting" || isStarting
  const isStoppingState = botStatus === "stopping" || isStopping
  const isTransitioning = isStartingState || isStoppingState
  const isActive = botActive === true && !isStoppingState
  const isInactive = (botActive === false || botActive === null) && !isStartingState

  const cooling = refreshCooldownSec > 0

  const handleRefreshClick = useCallback(async () => {
    const now = Date.now()
    if (now - lastRefreshRef.current < REFRESH_MIN_INTERVAL_MS) return
    if (cooling) return
    lastRefreshRef.current = now
    setRefreshSpinning(true)
    try {
      if (onRefresh) onRefresh()
      else await refreshBotStatus()
    } finally {
      setTimeout(() => setRefreshSpinning(false), 600)
    }
  }, [cooling, onRefresh, refreshBotStatus])

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3" data-testid="bot-status-bar">
        <div>
          {date && <p className="text-xs font-medium uppercase tracking-wider text-primary">{date}</p>}
          {title && <h1 className="text-2xl font-bold text-foreground">{title}</h1>}
        </div>
        <div className="flex flex-col items-end gap-2">
          {error && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive" data-testid="bot-status-error">
              <span>{error}</span>
              {insufficientTokens && onUpgradeClick && (
                <button
                  type="button"
                  onClick={() => { setError(null); onUpgradeClick() }}
                  className="rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground hover:opacity-90 transition-opacity"
                >
                  {t("sidebar.subscription")}
                </button>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            {/* Status badge */}
            <div
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium ${
                statusLoading || statusUnknown
                  ? "border-border bg-card text-muted-foreground"
                  : isTransitioning
                    ? "border-primary/40 bg-primary/5 text-primary"
                    : isActive
                      ? "live-badge"
                      : "border-border bg-card text-muted-foreground"
              }`}
              data-testid="bot-status-badge"
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  statusLoading || statusUnknown
                    ? "bg-muted-foreground"
                    : isStartingState
                      ? "bg-primary animate-pulse"
                      : isStoppingState
                        ? "bg-primary animate-pulse"
                        : botActive
                          ? "bg-emerald"
                          : "bg-muted-foreground"
                }`}
                aria-hidden
              />
              <span>
                {statusLoading
                  ? t("liveStatus.loadingStatus")
                  : statusUnknown
                    ? t("liveStatus.statusUnknown")
                    : isStartingState
                      ? t("liveStatus.starting")
                      : isStoppingState
                        ? t("liveStatus.stopping")
                        : botActive
                          ? t("liveStatus.botActive")
                          : t("liveStatus.botStopped")}
              </span>
            </div>

            <div className="flex items-center gap-2 border-l border-border pl-3">
              {/* Refresh */}
              <button
                onClick={handleRefreshClick}
                disabled={cooling || refreshSpinning}
                className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground hover:bg-muted/70 hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                title={cooling ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : "Refresh"}
              >
                <RefreshCw className={`h-3.5 w-3.5 shrink-0 ${refreshSpinning ? "animate-spin" : ""}`} />
                {t("liveStatus.refresh")}
              </button>

              {/* Exactly one action button: Starting spinner > Stopping spinner > Stop > Start */}
              {!statusLoading && !statusUnknown && (
                isStartingState ? (
                  <button
                    disabled
                    className="flex items-center gap-2 rounded-lg bg-primary/60 px-4 py-2 text-xs font-semibold text-primary-foreground opacity-80 cursor-not-allowed"
                  >
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                    {t("liveStatus.starting")}
                  </button>
                ) : isStoppingState ? (
                  <button
                    disabled
                    className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/8 px-4 py-2 text-xs font-semibold text-destructive opacity-70 cursor-not-allowed"
                  >
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                    {t("liveStatus.stopping")}
                  </button>
                ) : isActive ? (
                  <button
                    onClick={handleStop}
                    disabled={ctxCooldown > 0}
                    title={t("liveStatus.stopBotTitle")}
                    className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-2 text-xs font-semibold text-destructive hover:bg-destructive/20 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                    data-testid="bot-stop-button"
                  >
                    <Square className="h-3.5 w-3.5 shrink-0" />
                    {t("liveStatus.stopBot")}
                  </button>
                ) : isInactive ? (
                  <button
                    onClick={handleStart}
                    disabled={ctxCooldown > 0}
                    title={!isLoggedIn ? "Sign in to start the bot" : !hasApiKeys ? "Connect your Bitfinex API keys first" : t("liveStatus.startBotTitle")}
                    className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed transition-opacity"
                    data-testid="bot-start-button"
                  >
                    <Play className="h-3.5 w-3.5 shrink-0" />
                    {t("liveStatus.startBot")}
                  </button>
                ) : null
              )}
            </div>
          </div>
        </div>
      </div>

      {/* API Keys Popup */}
      {showApiKeysPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowApiKeysPopup(false)}>
          <div className="relative mx-4 w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl shadow-black/50" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => setShowApiKeysPopup(false)}
              className="absolute right-3 top-3 rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
                <KeyRound className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">Connect Your Bitfinex API</h3>
              <p className="text-sm text-muted-foreground">
                To start the lending bot, you need to connect your Bitfinex API keys first. Go to Settings to add your API key and secret.
              </p>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowApiKeysPopup(false)}
                  className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowApiKeysPopup(false)
                    onSettingsClick?.()
                  }}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 transition-opacity"
                >
                  Go to Settings
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
