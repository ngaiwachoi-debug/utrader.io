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
    isStarting, isStopping,
    refreshBotStatus, handleStart, handleStop,
    onUpgradeClick, isLoggedIn, hasApiKeys,
    showApiKeysPopup, setShowApiKeysPopup, onSettingsClick,
  } = ctx

  const statusLoading = loading || isRevalidating
  const statusUnknown = botActive === null

  const isStartingState = botStatus === "starting" || isStarting
  const isStoppingState = botStatus === "stopping" || isStopping
  const isActive = botActive === true && !isStoppingState
  const isInactive = botActive === false && !isStartingState

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
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive" data-testid="bot-status-error">
              <span>{error}</span>
              {insufficientTokens && onUpgradeClick && (
                <button
                  type="button"
                  onClick={() => { setError(null); onUpgradeClick() }}
                  className="rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  {t("sidebar.subscription")}
                </button>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            {/* Status badge */}
            <div
              className={`flex items-center gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs font-medium ${
                statusLoading || statusUnknown ? "text-muted-foreground" : botActive ? "text-primary" : "text-destructive"
              }`}
              data-testid="bot-status-badge"
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  statusLoading || statusUnknown
                    ? "bg-muted-foreground"
                    : isStartingState
                      ? "bg-amber-500 animate-pulse"
                      : isStoppingState
                        ? "bg-amber-500 animate-pulse"
                        : botActive
                          ? "bg-primary"
                          : "bg-destructive"
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

              {/* Start Bot: shown when bot is inactive (not starting/stopping/running) */}
              {isInactive && !statusLoading && !statusUnknown && (
                <button
                  onClick={handleStart}
                  disabled={isStartingState}
                  title={!isLoggedIn ? "Sign in to start the bot" : !hasApiKeys ? "Connect your Bitfinex API keys first" : t("liveStatus.startBotTitle")}
                  className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                  data-testid="bot-start-button"
                >
                  <Play className="h-3.5 w-3.5 shrink-0" />
                  {t("liveStatus.startBot")}
                </button>
              )}

              {/* Starting state: disabled spinner button */}
              {isStartingState && !statusLoading && (
                <button
                  disabled
                  className="flex items-center gap-2 rounded-lg bg-primary/70 px-4 py-2 text-xs font-semibold text-primary-foreground opacity-80 cursor-not-allowed transition-colors"
                >
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  {t("liveStatus.starting")}
                </button>
              )}

              {/* Stop Bot: shown only when bot is active (running) */}
              {isActive && !statusLoading && (
                <button
                  onClick={handleStop}
                  disabled={isStoppingState}
                  title={t("liveStatus.stopBotTitle")}
                  className="flex items-center gap-2 rounded-lg bg-destructive px-4 py-2 text-xs font-semibold text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                  data-testid="bot-stop-button"
                >
                  <Square className="h-3.5 w-3.5 shrink-0" />
                  {t("liveStatus.stopBot")}
                </button>
              )}

              {/* Stopping state: disabled spinner button */}
              {isStoppingState && !statusLoading && (
                <button
                  disabled
                  className="flex items-center gap-2 rounded-lg bg-destructive/70 px-4 py-2 text-xs font-semibold text-destructive-foreground opacity-80 cursor-not-allowed transition-colors"
                >
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  {t("liveStatus.stopping")}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* API Keys Popup */}
      {showApiKeysPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowApiKeysPopup(false)}>
          <div className="relative mx-4 w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => setShowApiKeysPopup(false)}
              className="absolute right-3 top-3 rounded-full p-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
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
                  className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-muted/50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowApiKeysPopup(false)
                    onSettingsClick?.()
                  }}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
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
