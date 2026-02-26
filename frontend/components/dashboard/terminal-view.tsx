"use client"

import { useEffect, useState, useRef } from "react"
import { Terminal } from "lucide-react"
import { useT } from "@/lib/i18n"
import { useCurrentUserId } from "@/lib/current-user-context"
import { getBackendToken } from "@/lib/auth"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"
const POLL_INTERVAL_MS = 10_000

export function TerminalView() {
  const t = useT()
  const userId = useCurrentUserId()
  const [lines, setLines] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (userId == null) {
      setLines([])
      setLoading(false)
      return
    }
    const fetchLogs = async () => {
      try {
        setError(null)
        const token = await getBackendToken()
        const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
        const res = await fetch(`${API_BASE}/terminal-logs/${userId}`, { credentials: "include", headers })
        if (res.ok) {
          const data = await res.json()
          setLines(Array.isArray(data.lines) ? data.lines : [])
        } else {
          setLines([])
        }
      } catch {
        setError("Failed to load terminal logs")
        setLines([])
      } finally {
        setLoading(false)
      }
    }
    fetchLogs()
    const interval = setInterval(fetchLogs, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [userId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [lines])

  if (userId == null) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold text-foreground">{t("dashboard.terminalBox")}</h1>
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted-foreground">Sign in to see the trading terminal.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("dashboard.terminalBox")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("dashboard.terminalDesc")}</p>
      </div>
      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">{t("dashboard.terminalBox")}</span>
          {loading && <span className="text-xs text-muted-foreground">Loading…</span>}
        </div>
        <div className="min-h-[320px] max-h-[60vh] overflow-y-auto bg-[#0d1117] p-4 font-mono text-xs text-[#e6edf3]">
          {lines.length === 0 && !loading ? (
            <pre className="whitespace-pre-wrap text-muted-foreground">{t("dashboard.terminalPlaceholder")}</pre>
          ) : (
            <>
              {lines.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))}
              <div ref={bottomRef} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
