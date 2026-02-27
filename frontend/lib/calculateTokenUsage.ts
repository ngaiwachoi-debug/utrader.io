/**
 * Token usage calculations for Settings "Token Usage" section.
 * Total Token Budget = purchased_tokens + REGISTRATION_BONUS (150).
 */

export const REGISTRATION_BONUS_TOKENS = 150

/**
 * Total token budget (purchased + registration bonus).
 */
export function calculateTotalBudget(purchasedTokens: number): number {
  return Math.max(0, Number(purchasedTokens) || 0) + REGISTRATION_BONUS_TOKENS
}

/**
 * Tokens used = total budget - remaining.
 */
export function calculateUsedTokens(totalBudget: number, remaining: number): number {
  const rem = Math.max(0, Number(remaining) || 0)
  return Math.max(0, totalBudget - rem)
}

/**
 * Usage percentage (0–100). Floored at 0, capped at 100.
 */
export function calculateUsagePercentage(used: number, total: number): number {
  if (total <= 0) return 0
  const pct = (used / total) * 100
  return Math.min(100, Math.max(0, pct))
}

/**
 * Format renewal date for display: MMM DD, YYYY in local time.
 * Returns "No renewal date (Free Plan)" if expiry is null/empty.
 */
export function formatRenewalDate(expiry: string | null | undefined): string {
  if (!expiry || typeof expiry !== "string") return "No renewal date (Free Plan)"
  try {
    const d = new Date(expiry)
    if (Number.isNaN(d.getTime())) return "No renewal date (Free Plan)"
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
  } catch {
    return "No renewal date (Free Plan)"
  }
}
