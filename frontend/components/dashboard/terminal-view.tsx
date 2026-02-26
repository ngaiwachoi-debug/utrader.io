"use client"

import { useEffect, useState } from "react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { getBackendToken } from "@/lib/auth"
import { Terminal } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"
const TERMINAL_POLL_MS = 10_000

/**
 * Terminal tab: shows trading box terminal output for all signed-in users.
 * Logs are cached; frontend polls every 10s.
 */
export function TerminalView() {
  const t = useT()
  const userId = useCurrentUserId()
  const [logLines, setLogLines] = useState<string[]>([])

  useEffect(() => {
    if (userId == null) {
      setLogLines([])
      return
    }
    const fetchLogs = async () => {
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      fetch(`${API_BASE}/terminal-logs/${userId}`, { credentials: "include", headers })
        .then((res) => (res.ok ? res.json() : { lines: [] }))
        .then((data) => setLogLines(Array.isArray(data.lines) ? data.lines : []))
        .catch(() => setLogLines([]))
    }
    fetchLogs()
    const interval = setInterval(fetchLogs, TERMINAL_POLL_MS)
    return () => clearInterval(interval)
  }, [userId])

  if (userId == null) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold text-foreground">{t("sidebar.terminal")}</h1>
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted-foreground">Sign in to see the trading terminal.</p>
        </div>
      </div>
    )
  }

  const terminalContent = logLines.length > 0 ? logLines.join("\n") : t("dashboard.terminalPlaceholder")

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("sidebar.terminal")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("dashboard.terminalDesc")}</p>
      </div>
      <div className="rounded-xl border border-border bg-card font-mono text-sm">
        <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">{t("dashboard.terminalBox")} (cached, refresh every {TERMINAL_POLL_MS / 1000}s)</span>
        </div>
        <pre className="overflow-auto p-4 min-h-[200px] text-muted-foreground whitespace-pre-wrap">
          {terminalContent}
        </pre>
      </div>
    </div>
  )
}
