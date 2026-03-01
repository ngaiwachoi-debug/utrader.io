"use client"

import { RefreshCw } from "lucide-react"
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

  const { botActive, error, setError, insufficientTokens, isStarting, isStopping, actionCooldownSec, refreshBotStatus, handleStart, handleStop, onUpgradeClick } = ctx
  const doRefresh = onRefresh ?? refreshBotStatus
  const cooling = refreshCooldownSec > 0
  const actionCooling = actionCooldownSec > 0

  const handleRefreshClick = async () => {
    if (cooling) return
    await doRefresh()
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        {date && <p className="text-xs font-medium uppercase tracking-wider text-emerald">{date}</p>}
        {title && <h1 className="text-2xl font-bold text-foreground">{title}</h1>}
      </div>
      <div className="flex flex-col items-end gap-2">
        {error && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            <span>{error}</span>
            {insufficientTokens && onUpgradeClick && (
              <button
                type="button"
                onClick={() => { setError(null); onUpgradeClick() }}
                className="rounded-md bg-emerald px-2.5 py-1 text-xs font-semibold text-primary-foreground hover:bg-emerald/90"
              >
                {t("sidebar.subscription")}
              </button>
            )}
          </div>
        )}
      <div className="flex items-center gap-2">
        <span
          className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${
            botActive ? "bg-emerald/10 text-emerald" : "bg-destructive/10 text-destructive"
          }`}
        >
          {botActive === null ? t("liveStatus.statusUnknown") : botActive ? t("liveStatus.botActive") : t("liveStatus.botStopped")}
        </span>
        <button
          onClick={handleRefreshClick}
          disabled={cooling}
          className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground hover:border-emerald/50 hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          title={cooling ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : undefined}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          {cooling ? t("liveStatus.refreshIn", { n: refreshCooldownSec }) : t("liveStatus.refresh")}
        </button>
        {!botActive && (
          <button
            onClick={handleStart}
            disabled={isStarting || actionCooling}
            title={t("liveStatus.startBotTitle")}
            className="rounded-lg bg-emerald px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-emerald/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {actionCooling ? t("liveStatus.waitBeforeAction", { n: actionCooldownSec }) : isStarting ? t("liveStatus.starting") : t("liveStatus.startBot")}
          </button>
        )}
        {botActive && (
          <button
            onClick={handleStop}
            disabled={isStopping || actionCooling}
            title={t("liveStatus.stopBotTitle")}
            className="rounded-lg bg-destructive px-3 py-2 text-xs font-semibold text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {actionCooling ? t("liveStatus.waitBeforeAction", { n: actionCooldownSec }) : isStopping ? t("liveStatus.stopping") : t("liveStatus.stopBot")}
          </button>
        )}
      </div>
      </div>
    </div>
  )
}
