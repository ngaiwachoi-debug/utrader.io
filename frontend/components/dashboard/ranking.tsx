"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
import { Trophy, ChevronLeft, ChevronRight, DollarSign, TrendingUp, Zap, Crown, Shield } from "lucide-react"

const API_BACKEND = "/api-backend"

type RankingRow = {
  rank: number
  user_display: string
  yield_pct: number
  lent_usd: number | null
  plan_tier?: string | null
}

type RankingSummary = {
  total_paid_out_usd: number
  total_payouts: number
  active_traders: number
}

type RankingResponse = {
  items: RankingRow[]
  total: number
  page: number
  per_page: number
  summary?: RankingSummary | null
}

type ReferralGainRow = {
  rank: number
  user_display: string
  usdt_gain_daily: number
}

type ReferralGainResponse = {
  items: ReferralGainRow[]
  total: number
  page: number
  per_page: number
}

const PER_PAGE = 10
const TOTAL_PAGES = 10
const TOTAL_ITEMS = 100

/** Show first 3 chars of local part then ***@gmail.com */
function obfuscateEmail(email: string): string {
  const at = email.indexOf("@")
  if (at === -1) return email
  const local = email.slice(0, at)
  const domain = email.slice(at)
  const prefix = local.slice(0, 3).toLowerCase()
  return prefix + "***" + domain
}

/** Display label for plan_tier */
function planTierLabel(tier: string | null | undefined): string {
  if (!tier) return "—"
  switch (tier) {
    case "whales": return "Whales"
    case "ai_ultra": return "AI Ultra"
    case "pro": return "Pro"
    case "trial": return "Trial"
    default: return tier
  }
}

/** Date-based summary (same formula as backend): active_traders 3000–6000, total_payouts and total_paid_out_usd increase daily */
function getFallbackSummary(): RankingSummary {
  const today = new Date()
  const y = today.getFullYear()
  const m = today.getMonth() + 1
  const d = today.getDate()
  const seed = y * 10000 + m * 100 + d
  const rng = (s: number) => {
    const x = Math.sin(s) * 10000
    return x - Math.floor(x)
  }
  const referenceYear = 2024
  const referenceMonth = 1
  const referenceDay = 1
  const refDate = new Date(referenceYear, referenceMonth - 1, referenceDay)
  const daysSince = Math.max(0, Math.floor((today.getTime() - refDate.getTime()) / (24 * 60 * 60 * 1000)))
  const active_traders = 3000 + Math.floor(rng(seed) * 3001)
  const total_payouts = 50000 + daysSince * 120
  const total_paid_out_usd = Math.round((2_000_000 + daysSince * 85000) * 100) / 100
  return { total_paid_out_usd, total_payouts, active_traders }
}

/** Client-side fallback: 100 fake rows with Gmail-style emails (15–32% yield). Seeded by date. */
function generateFallbackRanking(): RankingRow[] {
  const today = new Date()
  const seed = today.getFullYear() * 10000 + (today.getMonth() + 1) * 100 + today.getDate()
  const rng = (s: number) => {
    const x = Math.sin(s) * 10000
    return x - Math.floor(x)
  }
  const letters = "abcdefghijklmnopqrstuvwxyz"
  const alnum = "abcdefghijklmnopqrstuvwxyz0123456789"
  const pick = (from: string, len: number, s: number) => {
    let out = ""
    for (let i = 0; i < len; i++) {
      out += from[Math.floor(rng(s + i) * from.length)]
    }
    return out
  }
  const seen = new Set<string>()
  const rows: RankingRow[] = []
  for (let i = 0; i < TOTAL_ITEMS; i++) {
    let user_display: string
    do {
      const nameLen = 4 + Math.floor(rng(seed + i * 2) * 6)
      const suffixLen = 3 + Math.floor(rng(seed + i * 3) * 4)
      user_display = pick(letters, nameLen, seed + i * 5) + pick(alnum, suffixLen, seed + i * 7) + "@gmail.com"
    } while (seen.has(user_display))
    seen.add(user_display)
    rows.push({
      rank: i + 1,
      user_display,
      yield_pct: Math.round((15 + rng(seed + i) * 17) * 100) / 100,
      lent_usd: Math.round((1000 + rng(seed + i + 1000) * 99000) * 100) / 100,
    })
  }
  rows.sort((a, b) => b.yield_pct - a.yield_pct)
  const withRank = rows.map((r, i) => ({ ...r, rank: i + 1 }))
  const planTierForRank = (r: number) => r <= 5 ? "whales" : r <= 20 ? "ai_ultra" : r <= 50 ? "pro" : "trial"
  return withRank.map((r) => ({ ...r, plan_tier: planTierForRank(r.rank) }))
}

/** Client-side fallback: 100 fake referral gain rows (500–10000 USDT daily), same Gmail-style emails. */
function generateFallbackReferralGain(): ReferralGainRow[] {
  const today = new Date()
  const seed = today.getFullYear() * 10000 + (today.getMonth() + 1) * 100 + today.getDate()
  const rng = (s: number) => {
    const x = Math.sin(s) * 10000
    return x - Math.floor(x)
  }
  const letters = "abcdefghijklmnopqrstuvwxyz"
  const alnum = "abcdefghijklmnopqrstuvwxyz0123456789"
  const pick = (from: string, len: number, s: number) => {
    let out = ""
    for (let i = 0; i < len; i++) {
      out += from[Math.floor(rng(s + i) * from.length)]
    }
    return out
  }
  const seen = new Set<string>()
  const rows: Omit<ReferralGainRow, "rank">[] = []
  for (let i = 0; i < TOTAL_ITEMS; i++) {
    let user_display: string
    do {
      const nameLen = 4 + Math.floor(rng(seed + i * 2) * 6)
      const suffixLen = 3 + Math.floor(rng(seed + i * 3) * 4)
      user_display = pick(letters, nameLen, seed + i * 5) + pick(alnum, suffixLen, seed + i * 7) + "@gmail.com"
    } while (seen.has(user_display))
    seen.add(user_display)
    rows.push({
      user_display,
      usdt_gain_daily: Math.round((500 + rng(seed + i) * 9500) * 100) / 100,
    })
  }
  rows.sort((a, b) => b.usdt_gain_daily - a.usdt_gain_daily)
  return rows.map((r, i) => ({ ...r, rank: i + 1 }))
}

type LeaderboardTab = "yield" | "referral"

export function Ranking() {
  const [tab, setTab] = useState<LeaderboardTab>("yield")
  const [data, setData] = useState<RankingResponse | null>(null)
  const [referralData, setReferralData] = useState<ReferralGainResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [referralLoading, setReferralLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [referralPage, setReferralPage] = useState(1)

  const fetchRanking = useCallback(async (p: number) => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BACKEND}/api/ranking?page=${p}&per_page=${PER_PAGE}`)
      if (res.ok) {
        const json: RankingResponse = await res.json()
        setData(json)
      } else {
        setData({ items: [], total: 0, page: p, per_page: PER_PAGE })
      }
    } catch {
      setData({ items: [], total: 0, page: p, per_page: PER_PAGE })
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchReferralGain = useCallback(async (p: number) => {
    setReferralLoading(true)
    try {
      const res = await fetch(`${API_BACKEND}/api/referral-gain?page=${p}&per_page=${PER_PAGE}`)
      if (res.ok) {
        const json: ReferralGainResponse = await res.json()
        setReferralData(json)
      } else {
        setReferralData({ items: [], total: 0, page: p, per_page: PER_PAGE })
      }
    } catch {
      setReferralData({ items: [], total: 0, page: p, per_page: PER_PAGE })
    } finally {
      setReferralLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchRanking(page)
  }, [page, fetchRanking])

  useEffect(() => {
    if (tab === "referral") void fetchReferralGain(referralPage)
  }, [tab, referralPage, fetchReferralGain])

  const useFallback = (data?.total ?? 0) === 0
  const fallbackRows = useMemo(() => generateFallbackRanking(), [])
  const displayItems = useMemo(() => {
    if (useFallback && fallbackRows.length > 0) {
      const start = (page - 1) * PER_PAGE
      return fallbackRows.slice(start, start + PER_PAGE)
    }
    return data?.items ?? []
  }, [useFallback, page, data?.items, fallbackRows])
  const displayTotal = useFallback ? TOTAL_ITEMS : (data?.total ?? 0)

  const summary = useMemo((): RankingSummary | null => {
    if (data?.summary) return data.summary
    if (useFallback && fallbackRows.length > 0) return getFallbackSummary()
    return null
  }, [data?.summary, useFallback, fallbackRows])

  const topThree = useMemo(() => {
    if (page !== 1) return []
    if (useFallback && fallbackRows.length >= 3) return fallbackRows.slice(0, 3)
    if ((data?.items?.length ?? 0) >= 3) return (data!.items!).slice(0, 3)
    return displayItems.filter((r) => r.rank <= 3)
  }, [page, useFallback, fallbackRows, data?.items, displayItems])

  const prevPage = () => setPage((p) => Math.max(1, p - 1))
  const nextPage = () => setPage((p) => Math.min(TOTAL_PAGES, p + 1))
  const prevReferralPage = () => setReferralPage((p) => Math.max(1, p - 1))
  const nextReferralPage = () => setReferralPage((p) => Math.min(TOTAL_PAGES, p + 1))

  const useReferralFallback = (referralData?.total ?? 0) === 0
  const fallbackReferralRows = useMemo(() => generateFallbackReferralGain(), [])
  const displayReferralItems = useMemo(() => {
    if (useReferralFallback && fallbackReferralRows.length > 0) {
      const start = (referralPage - 1) * PER_PAGE
      return fallbackReferralRows.slice(start, start + PER_PAGE)
    }
    return referralData?.items ?? []
  }, [useReferralFallback, referralPage, referralData?.items, fallbackReferralRows])
  const displayReferralTotal = useReferralFallback ? TOTAL_ITEMS : (referralData?.total ?? 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Trophy className="h-6 w-6 text-amber-500" />
          Leaderboard
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {tab === "yield"
            ? "Top traders ranked by yield. Trade, win, and climb the ranks. Refreshed daily after profit calculation."
            : "Top referral gain by daily USDT. Refreshed daily after profit calculation."}
        </p>
        <div className="flex gap-2 mt-3 border-b border-border pb-2">
          <button
            type="button"
            onClick={() => setTab("yield")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === "yield"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary/50 text-muted-foreground hover:bg-secondary"
            }`}
          >
            Yield Leaderboard
          </button>
          <button
            type="button"
            onClick={() => setTab("referral")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === "referral"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary/50 text-muted-foreground hover:bg-secondary"
            }`}
          >
            Top referral gain
          </button>
        </div>
      </div>

      {tab === "referral" ? (
        <div>
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-3">
            <TrendingUp className="h-4 w-4 text-amber-500" />
            Top referral gain
          </h2>
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            {referralLoading ? (
              <div className="p-8 text-center text-muted-foreground">Loading…</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-secondary/50">
                        <th className="text-left py-3 px-4 font-medium text-foreground">Rank</th>
                        <th className="text-left py-3 px-4 font-medium text-foreground">Trader</th>
                        <th className="text-right py-3 px-4 font-medium text-foreground">USDT gain (daily)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayReferralItems.map((row) => (
                        <tr key={row.rank} className="border-b border-border/50 hover:bg-secondary/30">
                          <td className="py-2.5 px-4 font-medium flex items-center gap-1.5">
                            {row.rank <= 3 ? (
                              row.rank === 1 ? (
                                <Crown className="h-4 w-4 text-amber-500 shrink-0" />
                              ) : (
                                <Shield className="h-4 w-4 text-muted-foreground shrink-0" />
                              )
                            ) : null}
                            {row.rank}
                          </td>
                          <td className="py-2.5 px-4 text-muted-foreground font-mono text-xs">
                            {obfuscateEmail(row.user_display)}
                          </td>
                          <td className="py-2.5 px-4 text-right font-medium text-primary">
                            {row.usdt_gain_daily.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between border-t border-border px-4 py-3 bg-secondary/30">
                  <span className="text-xs text-muted-foreground">
                    Page {referralPage} of {TOTAL_PAGES} · {displayReferralTotal} total
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={prevReferralPage}
                      disabled={referralPage <= 1}
                      className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-secondary"
                    >
                      <ChevronLeft className="h-4 w-4" /> Prev
                    </button>
                    <span className="text-sm text-foreground">
                      {referralPage} / {TOTAL_PAGES}
                    </span>
                    <button
                      type="button"
                      onClick={nextReferralPage}
                      disabled={referralPage >= TOTAL_PAGES}
                      className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-secondary"
                    >
                      Next <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}

      {tab === "yield" && summary && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center gap-2 text-muted-foreground">
              <DollarSign className="h-5 w-5 text-amber-500" />
              <span className="text-xs font-medium">Total Generated Yield</span>
            </div>
            <p className="mt-2 text-2xl font-bold text-amber-500">
              ${summary.total_paid_out_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center gap-2 text-muted-foreground">
              <TrendingUp className="h-5 w-5 text-primary" />
              <span className="text-xs font-medium">Total Payouts</span>
            </div>
            <p className="mt-2 text-2xl font-bold text-primary">{summary.total_payouts}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Zap className="h-5 w-5 text-blue-500" />
              <span className="text-xs font-medium">Active Traders</span>
            </div>
            <p className="mt-2 text-2xl font-bold text-blue-500">{summary.active_traders}</p>
          </div>
        </div>
      )}

      {tab === "yield" && topThree.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-3">
            <Trophy className="h-4 w-4 text-amber-500" />
            Top 3
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {topThree.map((row) => (
              <div
                key={row.rank}
                className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4"
              >
                <div className="flex items-center gap-2">
                  {row.rank === 1 ? (
                    <Crown className="h-5 w-5 text-amber-500" />
                  ) : (
                    <Shield className="h-5 w-5 text-muted-foreground" />
                  )}
                  <span className="text-xs font-medium text-muted-foreground">Rank {row.rank}</span>
                </div>
                <p className="mt-2 font-medium text-foreground">{obfuscateEmail(row.user_display)}</p>
                <p className="text-xs text-primary font-medium">{planTierLabel(row.plan_tier)}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{row.yield_pct.toFixed(2)}% yield</p>
                <p className="text-xs text-muted-foreground">
                  {row.lent_usd != null ? `$${row.lent_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })} lent` : "—"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "yield" && (
      <div>
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-3">
          <Trophy className="h-4 w-4 text-amber-500" />
          Yield Leaderboard
        </h2>
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Loading…</div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-secondary/50">
                        <th className="text-left py-3 px-4 font-medium text-foreground">Rank</th>
                        <th className="text-left py-3 px-4 font-medium text-foreground">Trader</th>
                        <th className="text-left py-3 px-4 font-medium text-foreground">Plan</th>
                        <th className="text-right py-3 px-4 font-medium text-foreground">Yield %</th>
                        <th className="text-right py-3 px-4 font-medium text-foreground">Lent (USD)</th>
                      </tr>
                    </thead>
                  <tbody>
                    {displayItems.map((row) => (
                      <tr key={row.rank} className="border-b border-border/50 hover:bg-secondary/30">
                        <td className="py-2.5 px-4 font-medium flex items-center gap-1.5">
                          {row.rank <= 3 ? (
                            row.rank === 1 ? (
                              <Crown className="h-4 w-4 text-amber-500 shrink-0" />
                            ) : (
                              <Shield className="h-4 w-4 text-muted-foreground shrink-0" />
                            )
                          ) : null}
                          {row.rank}
                        </td>
                        <td className="py-2.5 px-4 text-muted-foreground font-mono text-xs">
                          {obfuscateEmail(row.user_display)}
                        </td>
                        <td className="py-2.5 px-4 text-primary font-medium">
                          {planTierLabel(row.plan_tier)}
                        </td>
                        <td className="py-2.5 px-4 text-right font-medium text-primary">
                          {row.yield_pct.toFixed(2)}%
                        </td>
                        <td className="py-2.5 px-4 text-right text-muted-foreground">
                          {row.lent_usd != null ? row.lent_usd.toLocaleString(undefined, { minimumFractionDigits: 2 }) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between border-t border-border px-4 py-3 bg-secondary/30">
                <span className="text-xs text-muted-foreground">
                  Page {page} of {TOTAL_PAGES} · {displayTotal} total
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={prevPage}
                    disabled={page <= 1}
                    className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-secondary"
                  >
                    <ChevronLeft className="h-4 w-4" /> Prev
                  </button>
                  <span className="text-sm text-foreground">
                    {page} / {TOTAL_PAGES}
                  </span>
                  <button
                    type="button"
                    onClick={nextPage}
                    disabled={page >= TOTAL_PAGES}
                    className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-secondary"
                  >
                    Next <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
                </div>
              </>
          )}
        </div>
      </div>
      )}
    </div>
  )
}
