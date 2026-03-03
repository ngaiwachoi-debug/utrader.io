"use client"

import { RefreshCw, Play, Square, Loader2 } from "lucide-react"
import { useT } from "@/lib/i18n"
import { useBotStatus } from "@/lib/bot-status-context"

type BotStatusBarProps = {
  /** Optional title next to the date (e.g. "Live Status", "Terminal") */
  title?: string
  /** Optional date line (e.g. "February 25, 2026") */
  date?: string
  /** Optional custom refresh handler (e.g. full refresh with cooldown on Live Status) */
  onRefresh?: () => Promise<void>
  /** Current cooldown seconds for Refresh (parent-owned when using onRefresh) */
  refreshCooldownSec?: number
}

/**
 * Shared bar: status badge (Bot Active / Bot Stopped) + optional Refresh + Start Bot / Stop Bot.
 * Shown on both Live Status and Terminal pages.
 */
export function BotStatusBar({ title, date, onRefresh, refreshCooldownSec = 0 }: BotStatusBarProps) {
  const t = useT()
  const ctx = useBotStatus()

  if (!ctx) return null

  const { botActive, loading, isRevalidating, error, setError, insufficientTokens, isStarting, isStopping, actionCooldownSec, refreshBotStatus, handleStart, handleStop, onUpgradeClick } = ctx
  const doRefresh = onRefresh ?? refreshBotStatus
  const cooling = refreshCooldownSec > 0
  const actionCooling = actionCooldownSec > 0
  const statusLoading = loading || isRevalidating
  const statusUnknown = botActive === null
  /** Show Start/Stop only when status is known and not loading (unless there's an error so user can retry) */
  const showActions = !statusLoading && !statusUnknown

  const handleRefreshClick = async () => {
    if (cooling) return
    await doRefresh()
  }

  return (
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
        {/* Status block: dot + label */}
        <div
          className={`flex items-center gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs font-medium ${
            statusLoading || statusUnknown ? "text-muted-foreground" : botActive ? "text-primary" : "text-destructive"
          }`}
          data-testid="bot-status-badge"
        >
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${
              statusLoading || statusUnknown ? "bg-muted-foreground" : botActive ? "bg-primary" : "bg-destructive"
            }`}
            aria-hidden
          />
          <span>
            {statusLoading ? t("liveStatus.loadingStatus") : statusUnknown ? t("liveStatus.statusUnknown") : botActive ? t("liveStatus.botActive") : t("liveStatus.botStopped")}
          </span>
        </div>

        <div className="flex items-center gap-2 border-l border-border pl-3">
          {/* Refresh */}
          <button
            onClick={handleRefreshClick}
            disabled={cooling}
            className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground hover:bg-muted/70 hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            title={cooling ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : undefined}
          >
            <RefreshCw className="h-3.5 w-3.5 shrink-0" />
            {cooling ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : t("liveStatus.refresh")}
          </button>

          {/* Start / Stop: only when status is known and not loading */}
          {showActions && botActive === false && (
            <button
              onClick={handleStart}
              disabled={isStarting || actionCooling}
              title={t("liveStatus.startBotTitle")}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
              data-testid="bot-start-button"
            >
              {isStarting ? (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5 shrink-0" />
              )}
              {actionCooling ? t("liveStatus.waitBeforeAction", { n: actionCooldownSec }) : isStarting ? t("liveStatus.starting") : t("liveStatus.startBot")}
            </button>
          )}
          {showActions && botActive === true && (
            <button
              onClick={handleStop}
              disabled={isStopping || actionCooling}
              title={t("liveStatus.stopBotTitle")}
              className="flex items-center gap-2 rounded-lg bg-destructive px-4 py-2 text-xs font-semibold text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
              data-testid="bot-stop-button"
            >
              {isStopping ? (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
              ) : (
                <Square className="h-3.5 w-3.5 shrink-0" />
              )}
              {actionCooling ? t("liveStatus.waitBeforeAction", { n: actionCooldownSec }) : isStopping ? t("liveStatus.stopping") : t("liveStatus.stopBot")}
            </button>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}
