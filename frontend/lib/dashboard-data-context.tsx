"use client"

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import { getBackendToken } from "@/lib/auth"

const API_BACKEND = "/api-backend"

const FRESH_MS = 2 * 60 * 1000
const STALE_MS = 10 * 60 * 1000
const STORAGE_PREFIX = "bifinexbot_dashboard"

export type CreditDetail = { id: number; symbol: string; amount: number; rate: number; period: number; amount_usd: number }

export type WalletSummary = {
  total_usd_all: number
  usd_only: number
  per_currency: Record<string, number>
  per_currency_usd: Record<string, number>
  lent_per_currency?: Record<string, number>
  offers_per_currency?: Record<string, number>
  lent_per_currency_usd?: Record<string, number>
  offers_per_currency_usd?: Record<string, number>
  idle_per_currency_usd?: Record<string, number>
  total_lent_usd?: number
  total_offers_usd?: number
  idle_usd?: number
  weighted_avg_apr_pct?: number
  est_daily_earnings_usd?: number
  yield_over_total_pct?: number
  credits_count?: number
  offers_count?: number
  credits_detail?: CreditDetail[]
  offers_detail?: CreditDetail[]
}

export type BotStatsData = { active: boolean; total_loaned: number }
export type UserStatusData = { tokens_remaining: number | null; plan_tier: string | null; has_keys?: boolean }

export type LendingStatsTrade = {
  id: number
  currency: string
  mts_create: number
  amount: number
  rate: number
  period: number
  interest_usd: number
}

export type LendingStatsCalculationBreakdown = {
  trades_count: number
  per_currency: Array<{ currency: string; interest_ccy: number; ticker_price_usd: number; interest_usd: number }>
  total_gross_usd: number
  formula_note?: string
}

export type LendingStatsData = {
  gross_profit: number
  net_profit: number
  trades: LendingStatsTrade[]
  total_trades_count: number
  calculation_breakdown: LendingStatsCalculationBreakdown | null
}

export type ReferralInfo = {
  referral_code: string
  referrer_id: number | null
  referrer_email: string | null
  total_usdt_credit_earned: number
  referred_users_count?: number
  usdt_withdraw_address?: string | null
}

export type ReferralDownlineRow = {
  user_id: number
  email_masked: string
  created_at: string | null
  total_usdt_earned_from_them: number
}

export type ReferralUsdtCredit = {
  usdt_credit: number
  locked_pending: number
  available: number
}

export type ReferralWithdrawalRow = {
  id: number
  amount: number
  to_address?: string
  address?: string
  status: string
  created_at: string | null
  processed_at: string | null
  rejection_note?: string | null
}

export type ReferralRewardHistoryRow = {
  created_at: string | null
  burning_user_id: number
  downline_email: string | null
  amount_usdt_credit: number
  level?: number
}

export type ReferralUsdtData = {
  referralInfo: ReferralInfo | null
  usdtCredit: ReferralUsdtCredit | null
  withdrawals: ReferralWithdrawalRow[]
  rewardHistory: ReferralRewardHistoryRow[]
  downline: ReferralDownlineRow[]
}

type CacheEntry<T> = {
  data: T | null
  fetchedAt: number
  error: string | null
  source: "live" | "cache" | null
  rateLimited?: boolean
}

type WalletCacheEntry = CacheEntry<WalletSummary> & { errorMessage?: string | null }
type BotStatsCacheEntry = CacheEntry<BotStatsData>
type UserStatusCacheEntry = CacheEntry<UserStatusData>
type LendingStatsCacheEntry = CacheEntry<LendingStatsData>
type ReferralDataCacheEntry = CacheEntry<ReferralUsdtData>

type CacheState = {
  wallets: Record<number, WalletCacheEntry>
  botStats: Record<number, BotStatsCacheEntry>
  userStatus: Record<number, UserStatusCacheEntry>
  lendingStats: Record<number, LendingStatsCacheEntry>
  referralData: Record<number, ReferralDataCacheEntry>
  version: number
}

type DashboardDataContextValue = {
  getWallets: (userId: number) => {
    data: WalletSummary | null
    loading: boolean
    error: string | null
    source: "live" | "cache" | null
    rateLimited: boolean
    isRevalidating: boolean
    refetch: () => Promise<void>
  }
  getBotStats: (userId: number) => {
    data: BotStatsData | null
    loading: boolean
    error: string | null
    isRevalidating: boolean
    refetch: () => Promise<void>
  }
  getUserStatus: (userId: number) => {
    data: UserStatusData | null
    loading: boolean
    error: string | null
    refetch: () => Promise<void>
  }
  getLendingStats: (userId: number) => {
    data: LendingStatsData | null
    loading: boolean
    error: string | null
    source: "live" | "cache" | null
    rateLimited: boolean
    isRevalidating: boolean
    refetch: () => Promise<void>
  }
  getReferralData: (userId: number) => {
    data: ReferralUsdtData | null
    loading: boolean
    error: string | null
    isRevalidating: boolean
    refetch: () => Promise<void>
  }
  prefetch: (userId: number) => void
}

const initialState: CacheState = { wallets: {}, botStats: {}, userStatus: {}, lendingStats: {}, referralData: {}, version: 0 }
const DashboardDataContext = createContext<DashboardDataContextValue | null>(null)

function loadFromStorage<T>(key: string): T | null {
  if (typeof window === "undefined") return null
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function saveToStorage(key: string, value: unknown): void {
  if (typeof window === "undefined") return
  try {
    sessionStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore
  }
}

function normalizeWalletSummary(w: Record<string, unknown>): WalletSummary {
  return {
    total_usd_all: Number(w.total_usd_all) || 0,
    usd_only: Number(w.usd_only) || 0,
    per_currency: (w.per_currency as Record<string, number>) || {},
    per_currency_usd: (w.per_currency_usd as Record<string, number>) || {},
    lent_per_currency: (w.lent_per_currency as Record<string, number>) || {},
    offers_per_currency: (w.offers_per_currency as Record<string, number>) || {},
    lent_per_currency_usd: (w.lent_per_currency_usd as Record<string, number>) || {},
    offers_per_currency_usd: (w.offers_per_currency_usd as Record<string, number>) || {},
    idle_per_currency_usd: (w.idle_per_currency_usd as Record<string, number>) || {},
    total_lent_usd: Number(w.total_lent_usd) ?? 0,
    total_offers_usd: Number(w.total_offers_usd) ?? 0,
    idle_usd: Number(w.idle_usd) ?? 0,
    weighted_avg_apr_pct: Number(w.weighted_avg_apr_pct) ?? 0,
    est_daily_earnings_usd: Number(w.est_daily_earnings_usd) ?? 0,
    yield_over_total_pct: Number(w.yield_over_total_pct) ?? 0,
    credits_count: Number(w.credits_count) ?? 0,
    offers_count: Number(w.offers_count) ?? 0,
    credits_detail: Array.isArray(w.credits_detail) ? (w.credits_detail as CreditDetail[]) : [],
    offers_detail: Array.isArray(w.offers_detail) ? (w.offers_detail as CreditDetail[]) : [],
  }
}

function normalizeLendingStats(raw: Record<string, unknown>): LendingStatsData {
  const trades = Array.isArray(raw.trades) ? (raw.trades as LendingStatsTrade[]) : []
  let gross =
    typeof raw.gross_profit === "number" && (raw.gross_profit as number) > 0
      ? (raw.gross_profit as number)
      : typeof raw.db_snapshot_gross === "number" && (raw.db_snapshot_gross as number) > 0
        ? (raw.db_snapshot_gross as number)
        : 0
  const net =
    typeof raw.net_profit === "number" && (raw.net_profit as number) > 0
      ? (raw.net_profit as number)
      : gross > 0
        ? Math.round(gross * (1 - 0.15) * 100) / 100
        : 0
  const total_trades_count =
    typeof raw.total_trades_count === "number" ? (raw.total_trades_count as number) : trades.length
  const calculation_breakdown = raw.calculation_breakdown as LendingStatsCalculationBreakdown | null | undefined
  return {
    gross_profit: gross,
    net_profit: net,
    trades,
    total_trades_count,
    calculation_breakdown: calculation_breakdown ?? null,
  }
}

export function DashboardDataProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<CacheState>(initialState)
  const inFlightWallets = useRef<Record<number, Promise<void>>>({})
  const inFlightBotStats = useRef<Record<number, Promise<void>>>({})
  const inFlightUserStatus = useRef<Record<number, Promise<void>>>({})
  const inFlightLendingStats = useRef<Record<number, Promise<void>>>({})
  const inFlightReferralData = useRef<Record<number, Promise<void>>>({})

  const updateState = useCallback((updater: (prev: CacheState) => CacheState) => {
    setState((prev) => ({ ...updater(prev), version: prev.version + 1 }))
  }, [])

  const fetchWallets = useCallback(
    async (userId: number, force?: boolean): Promise<void> => {
      const existing = state.wallets[userId]
      if (!force && existing?.data != null) {
        const age = Date.now() - existing.fetchedAt
        if (age < FRESH_MS) return
      }
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/wallets/${userId}`, { credentials: "include", headers })
      const source = res.headers.get("X-Data-Source") === "cache" ? "cache" : "live"
      const rateLimited = res.headers.get("X-Rate-Limited") === "true"
      if (res.ok) {
        const raw = await res.json().catch(() => ({}))
        const data = normalizeWalletSummary(raw)
        updateState((prev) => ({
          ...prev,
          wallets: {
            ...prev.wallets,
            [userId]: { data, fetchedAt: Date.now(), error: null, source, rateLimited, errorMessage: null },
          },
        }))
        saveToStorage(`${STORAGE_PREFIX}:${userId}:wallets`, { data, fetchedAt: Date.now(), source })
      } else {
        const incomplete = res.headers.get("X-Data-Incomplete") === "true"
        const errorMessage = res.status === 503 || incomplete ? "Data incomplete" : "Connect API keys"
        updateState((prev) => ({
          ...prev,
          wallets: {
            ...prev.wallets,
            [userId]: {
              data: existing?.data ?? null,
              fetchedAt: Date.now(),
              error: errorMessage,
              source: null,
              rateLimited: false,
              errorMessage: errorMessage,
            },
          },
        }))
      }
    },
    [state.wallets, updateState]
  )

  const fetchBotStats = useCallback(
    async (userId: number, force?: boolean): Promise<void> => {
      const existing = state.botStats[userId]
      if (!force && existing?.data != null) {
        const age = Date.now() - existing.fetchedAt
        if (age < FRESH_MS) return
      }
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/bot-stats/${userId}`, { credentials: "include", headers })
      if (res.ok) {
        const data = await res.json().catch(() => ({}))
        const active = Boolean(data.active)
        const total_loaned = parseFloat(String(data.total_loaned ?? "0").replace(/,/g, ""))
        updateState((prev) => ({
          ...prev,
          botStats: {
            ...prev.botStats,
            [userId]: {
              data: { active, total_loaned: Number.isFinite(total_loaned) ? total_loaned : 0 },
              fetchedAt: Date.now(),
              error: null,
              source: "live",
            },
          },
        }))
        saveToStorage(`${STORAGE_PREFIX}:${userId}:botStats`, {
          data: { active, total_loaned: Number.isFinite(total_loaned) ? total_loaned : 0 },
          fetchedAt: Date.now(),
        })
      } else {
        updateState((prev) => ({
          ...prev,
          botStats: {
            ...prev.botStats,
            [userId]: {
              data: existing?.data ?? null,
              fetchedAt: Date.now(),
              error: "Failed to load",
              source: null,
            },
          },
        }))
      }
    },
    [state.botStats, updateState]
  )

  const fetchUserStatus = useCallback(
    async (userId: number, force?: boolean): Promise<void> => {
      const existing = state.userStatus[userId]
      if (!force && existing?.data != null) {
        const age = Date.now() - existing.fetchedAt
        if (age < FRESH_MS) return
      }
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/user-status/${userId}`, { credentials: "include", headers })
      if (res.ok) {
        const data = await res.json().catch(() => ({}))
        const tokens_remaining = typeof data.tokens_remaining === "number" ? data.tokens_remaining : null
        const plan_tier = typeof data.plan_tier === "string" ? data.plan_tier : null
        const has_keys = data.has_keys === true
        updateState((prev) => ({
          ...prev,
          userStatus: {
            ...prev.userStatus,
            [userId]: {
              data: { tokens_remaining, plan_tier, has_keys },
              fetchedAt: Date.now(),
              error: null,
              source: "live",
            },
          },
        }))
      } else {
        updateState((prev) => ({
          ...prev,
          userStatus: {
            ...prev.userStatus,
            [userId]: {
              data: existing?.data ?? null,
              fetchedAt: Date.now(),
              error: "Failed to load",
              source: null,
            },
          },
        }))
      }
    },
    [state.userStatus, updateState]
  )

  const fetchLendingStats = useCallback(
    async (userId: number, force?: boolean): Promise<void> => {
      const existing = state.lendingStats[userId]
      if (!force && existing?.data != null) {
        const age = Date.now() - existing.fetchedAt
        if (age < FRESH_MS) return
      }
      const token = await getBackendToken()
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${API_BACKEND}/stats/${userId}/lending`, { credentials: "include", headers })
      const source = res.headers.get("X-Data-Source") === "cache" ? "cache" : "live"
      const rateLimited = res.headers.get("X-Rate-Limited") === "true"
      if (res.ok) {
        let raw: Record<string, unknown> = await res.json().catch(() => ({}))
        if (typeof raw.gross_profit === "number" && raw.gross_profit === 0) {
          const dbRes = await fetch(`${API_BACKEND}/stats/${userId}/lending?source=db`, { credentials: "include", headers })
          if (dbRes.ok) {
            const dbData = await dbRes.json().catch(() => ({}))
            if (typeof dbData.gross_profit === "number" && dbData.gross_profit > 0) raw = dbData
          }
        }
        let data = normalizeLendingStats(raw)
        if (data.trades.length === 0 && data.gross_profit > 0) {
          try {
            const ftRes = await fetch(`${API_BACKEND}/api/funding-trades`, { credentials: "include", headers })
            if (ftRes.ok) {
              const ftData = await ftRes.json().catch(() => ({}))
              const trades = Array.isArray(ftData?.trades) ? (ftData.trades as LendingStatsTrade[]) : []
              data = { ...data, trades, total_trades_count: data.total_trades_count || trades.length }
            }
          } catch {
            // keep trades empty
          }
        }
        updateState((prev) => ({
          ...prev,
          lendingStats: {
            ...prev.lendingStats,
            [userId]: { data, fetchedAt: Date.now(), error: null, source, rateLimited },
          },
        }))
        saveToStorage(`${STORAGE_PREFIX}:${userId}:lendingStats`, { data, fetchedAt: Date.now(), source })
      } else {
        updateState((prev) => ({
          ...prev,
          lendingStats: {
            ...prev.lendingStats,
            [userId]: {
              data: existing?.data ?? null,
              fetchedAt: Date.now(),
              error: "Failed to load",
              source: null,
              rateLimited: false,
            },
          },
        }))
      }
    },
    [state.lendingStats, updateState]
  )

  const fetchReferralData = useCallback(
    async (userId: number, force?: boolean): Promise<void> => {
      const existing = state.referralData[userId]
      if (!force && existing?.data != null) {
        const age = Date.now() - existing.fetchedAt
        if (age < FRESH_MS) return
      }
      const token = await getBackendToken()
      if (!token) {
        updateState((prev) => ({
          ...prev,
          referralData: {
            ...prev.referralData,
            [userId]: {
              data: existing?.data ?? null,
              fetchedAt: Date.now(),
              error: "Not authenticated",
              source: null,
            },
          },
        }))
        return
      }
      const headers: HeadersInit = { Authorization: `Bearer ${token}` }
      try {
        const [refRes, creditRes, histRes, rewardRes, downlineRes] = await Promise.all([
          fetch(`${API_BACKEND}/api/v1/user/referral-info`, { credentials: "include", headers }),
          fetch(`${API_BACKEND}/api/v1/user/usdt-credit`, { credentials: "include", headers }),
          fetch(`${API_BACKEND}/api/v1/user/usdt-withdraw-history`, { credentials: "include", headers }),
          fetch(`${API_BACKEND}/api/v1/user/referral-reward-history?limit=50`, { credentials: "include", headers }),
          fetch(`${API_BACKEND}/api/v1/user/referral-downline`, { credentials: "include", headers }),
        ])
        const referralInfo: ReferralInfo | null = refRes.ok ? await refRes.json().catch(() => null) : null
        const usdtCredit: ReferralUsdtCredit | null = creditRes.ok ? await creditRes.json().catch(() => null) : null
        const withdrawals: ReferralWithdrawalRow[] = histRes.ok ? await histRes.json().catch(() => []) : []
        const rewardHistory: ReferralRewardHistoryRow[] = rewardRes.ok ? await rewardRes.json().catch(() => []) : []
        const downline: ReferralDownlineRow[] = downlineRes.ok ? await downlineRes.json().catch(() => []) : []
        const data: ReferralUsdtData = {
          referralInfo,
          usdtCredit,
          withdrawals: Array.isArray(withdrawals) ? withdrawals : [],
          rewardHistory: Array.isArray(rewardHistory) ? rewardHistory : [],
          downline: Array.isArray(downline) ? downline : [],
        }
        updateState((prev) => ({
          ...prev,
          referralData: {
            ...prev.referralData,
            [userId]: { data, fetchedAt: Date.now(), error: null, source: "live" },
          },
        }))
        saveToStorage(`${STORAGE_PREFIX}:${userId}:referralData`, { data, fetchedAt: Date.now(), source: "live" })
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "Failed to load referral data"
        updateState((prev) => ({
          ...prev,
          referralData: {
            ...prev.referralData,
            [userId]: {
              data: existing?.data ?? null,
              fetchedAt: Date.now(),
              error: errorMessage,
              source: null,
            },
          },
        }))
      }
    },
    [state.referralData, updateState]
  )

  const getWalletsEntry = useCallback((userId: number): WalletCacheEntry | null => {
    const entry = state.wallets[userId]
    if (entry) return entry
    if (typeof window === "undefined") return null
    const stored = loadFromStorage<{ data: WalletSummary; fetchedAt: number; source: "live" | "cache" }>(
      `${STORAGE_PREFIX}:${userId}:wallets`
    )
    if (!stored?.data) return null
    return {
      data: stored.data,
      fetchedAt: stored.fetchedAt,
      error: null,
      source: stored.source ?? null,
      rateLimited: false,
      errorMessage: null,
    }
  }, [state.wallets])

  const getBotStatsEntry = useCallback((userId: number): BotStatsCacheEntry | null => {
    const entry = state.botStats[userId]
    if (entry) return entry
    if (typeof window === "undefined") return null
    const stored = loadFromStorage<{ data: BotStatsData; fetchedAt: number }>(
      `${STORAGE_PREFIX}:${userId}:botStats`
    )
    if (!stored?.data) return null
    return {
      data: stored.data,
      fetchedAt: stored.fetchedAt,
      error: null,
      source: "live",
    }
  }, [state.botStats])

  const getLendingStatsEntry = useCallback((userId: number): LendingStatsCacheEntry | null => {
    const entry = state.lendingStats[userId]
    if (entry) return entry
    if (typeof window === "undefined") return null
    const stored = loadFromStorage<{ data: LendingStatsData; fetchedAt: number; source: "live" | "cache" }>(
      `${STORAGE_PREFIX}:${userId}:lendingStats`
    )
    if (!stored?.data) return null
    return {
      data: stored.data,
      fetchedAt: stored.fetchedAt,
      error: null,
      source: stored.source ?? null,
      rateLimited: false,
    }
  }, [state.lendingStats])

  const getReferralDataEntry = useCallback((userId: number): ReferralDataCacheEntry | null => {
    const entry = state.referralData[userId]
    if (entry) return entry
    if (typeof window === "undefined") return null
    const stored = loadFromStorage<{ data: ReferralUsdtData; fetchedAt: number; source: "live" | "cache" }>(
      `${STORAGE_PREFIX}:${userId}:referralData`
    )
    if (!stored?.data) return null
    return {
      data: stored.data,
      fetchedAt: stored.fetchedAt,
      error: null,
      source: stored.source ?? null,
    }
  }, [state.referralData])

  const needLendingStatsFetch = useCallback((entry: LendingStatsCacheEntry | null) => {
    if (!entry) return { needFetch: true, isRevalidating: false }
    const age = Date.now() - entry.fetchedAt
    if (age < FRESH_MS) return { needFetch: false, isRevalidating: false }
    if (age <= STALE_MS) return { needFetch: true, isRevalidating: true }
    return { needFetch: true, isRevalidating: !entry.data }
  }, [])

  const needWalletsFetch = useCallback((entry: WalletCacheEntry | null) => {
    if (!entry) return { needFetch: true, isRevalidating: false }
    const age = Date.now() - entry.fetchedAt
    if (age < FRESH_MS) return { needFetch: false, isRevalidating: false }
    if (age <= STALE_MS) return { needFetch: true, isRevalidating: true }
    return { needFetch: true, isRevalidating: !entry.data }
  }, [])

  const needBotStatsFetch = useCallback((entry: BotStatsCacheEntry | null) => {
    if (!entry) return { needFetch: true, isRevalidating: false }
    const age = Date.now() - entry.fetchedAt
    if (age < FRESH_MS) return { needFetch: false, isRevalidating: false }
    if (age <= STALE_MS) return { needFetch: true, isRevalidating: true }
    return { needFetch: true, isRevalidating: !entry.data }
  }, [])

  const needReferralDataFetch = useCallback((entry: ReferralDataCacheEntry | null) => {
    if (!entry) return { needFetch: true, isRevalidating: false }
    const age = Date.now() - entry.fetchedAt
    if (age < FRESH_MS) return { needFetch: false, isRevalidating: false }
    if (age <= STALE_MS) return { needFetch: true, isRevalidating: true }
    return { needFetch: true, isRevalidating: !entry.data }
  }, [])

  const ensureUserStatus = useCallback(
    (userId: number): boolean => {
      const entry = state.userStatus[userId]
      if (!entry) return true
      const age = Date.now() - entry.fetchedAt
      return age >= FRESH_MS
    },
    [state.userStatus]
  )

  const getWallets = useCallback(
    (userId: number) => {
      const entry = getWalletsEntry(userId)
      const { needFetch, isRevalidating } = needWalletsFetch(entry)
      const inFlight = !!inFlightWallets.current[userId]
      const loading = !entry?.data && (needFetch || inFlight)
      return {
        data: entry?.data ?? null,
        loading,
        error: entry?.errorMessage ?? entry?.error ?? null,
        source: entry?.source ?? null,
        rateLimited: entry?.rateLimited ?? false,
        isRevalidating: isRevalidating && !!entry?.data,
        refetch: () => fetchWallets(userId, true),
      }
    },
    [state.wallets, state.version, getWalletsEntry, needWalletsFetch]
  )

  const getBotStats = useCallback(
    (userId: number) => {
      const entry = getBotStatsEntry(userId)
      const { needFetch, isRevalidating } = needBotStatsFetch(entry)
      const inFlight = !!inFlightBotStats.current[userId]
      const loading = !entry?.data && (needFetch || inFlight)
      return {
        data: entry?.data ?? null,
        loading,
        error: entry?.error ?? null,
        isRevalidating: isRevalidating && !!entry?.data,
        refetch: () => fetchBotStats(userId, true),
      }
    },
    [state.botStats, state.version, getBotStatsEntry, needBotStatsFetch, fetchBotStats]
  )

  const getUserStatus = useCallback(
    (userId: number) => {
      const needFetch = ensureUserStatus(userId)
      const entry = state.userStatus[userId]
      const inFlight = !!inFlightUserStatus.current[userId]
      const loading = !entry?.data && (needFetch || inFlight)
      return {
        data: entry?.data ?? null,
        loading,
        error: entry?.error ?? null,
        refetch: () => fetchUserStatus(userId, true),
      }
    },
    [state.userStatus, state.version, ensureUserStatus, fetchUserStatus]
  )

  const getLendingStats = useCallback(
    (userId: number) => {
      const entry = getLendingStatsEntry(userId)
      const { needFetch, isRevalidating } = needLendingStatsFetch(entry)
      const inFlight = !!inFlightLendingStats.current[userId]
      const loading = !entry?.data && (needFetch || inFlight)
      return {
        data: entry?.data ?? null,
        loading,
        error: entry?.error ?? null,
        source: entry?.source ?? null,
        rateLimited: entry?.rateLimited ?? false,
        isRevalidating: isRevalidating && !!entry?.data,
        refetch: () => fetchLendingStats(userId, true),
      }
    },
    [state.lendingStats, state.version, getLendingStatsEntry, needLendingStatsFetch]
  )

  const getReferralData = useCallback(
    (userId: number) => {
      const entry = getReferralDataEntry(userId)
      const { needFetch, isRevalidating } = needReferralDataFetch(entry)
      const inFlight = !!inFlightReferralData.current[userId]
      const loading = !entry?.data && (needFetch || inFlight)
      return {
        data: entry?.data ?? null,
        loading,
        error: entry?.error ?? null,
        isRevalidating: isRevalidating && !!entry?.data,
        refetch: () => fetchReferralData(userId, true),
      }
    },
    [state.referralData, state.version, getReferralDataEntry, needReferralDataFetch]
  )

  const prefetch = useCallback(
    (userId: number) => {
      if (!inFlightWallets.current[userId]) inFlightWallets.current[userId] = fetchWallets(userId)
      if (!inFlightBotStats.current[userId]) inFlightBotStats.current[userId] = fetchBotStats(userId)
      if (!inFlightUserStatus.current[userId]) inFlightUserStatus.current[userId] = fetchUserStatus(userId)
      if (!inFlightLendingStats.current[userId]) inFlightLendingStats.current[userId] = fetchLendingStats(userId)
      if (!inFlightReferralData.current[userId]) {
        inFlightReferralData.current[userId] = fetchReferralData(userId).finally(() => {
          delete inFlightReferralData.current[userId]
        })
      }
    },
    [fetchWallets, fetchBotStats, fetchUserStatus, fetchLendingStats, fetchReferralData]
  )

  const value: DashboardDataContextValue = {
    getWallets,
    getBotStats,
    getUserStatus,
    getLendingStats,
    getReferralData,
    prefetch,
  }

  return <DashboardDataContext.Provider value={value}>{children}</DashboardDataContext.Provider>
}

export function useDashboardData() {
  const ctx = useContext(DashboardDataContext)
  if (!ctx) throw new Error("useDashboardData must be used within DashboardDataProvider")
  return ctx
}

export function useWallets(userId: number) {
  const { getWallets } = useDashboardData()
  return getWallets(userId)
}

export function useBotStats(userId: number) {
  const { getBotStats, prefetch } = useDashboardData()
  useEffect(() => {
    if (userId != null && userId > 0) prefetch(userId)
  }, [userId, prefetch])
  return getBotStats(userId)
}

export function useUserStatus(userId: number) {
  const { getUserStatus, prefetch } = useDashboardData()
  useEffect(() => {
    if (userId != null && userId > 0) prefetch(userId)
  }, [userId, prefetch])
  return getUserStatus(userId)
}

export function useLendingStats(userId: number) {
  const { getLendingStats, prefetch } = useDashboardData()
  useEffect(() => {
    if (userId != null && userId > 0) prefetch(userId)
  }, [userId, prefetch])
  return getLendingStats(userId)
}

export function useReferralData(userId: number) {
  const { getReferralData, prefetch } = useDashboardData()
  useEffect(() => {
    if (userId != null && userId > 0) prefetch(userId)
  }, [userId, prefetch])
  return getReferralData(userId)
}
