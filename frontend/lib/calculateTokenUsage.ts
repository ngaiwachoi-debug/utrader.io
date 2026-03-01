/**
 * Token usage: remaining = total_tokens_added - total_tokens_deducted.
 * Total budget = total_tokens_added; used = total_tokens_deducted.
 */

/**
 * Total token budget (from API total_tokens_added).
 */
export function calculateTotalBudget(totalTokensAdded: number): number {
  return Math.max(0, Number(totalTokensAdded) ?? 0)
}

/**
 * Tokens used (from API total_tokens_deducted, or total budget - remaining).
 */
export function calculateUsedTokens(totalBudget: number, remaining: number): number {
  const rem = Math.max(0, Number(remaining) ?? 0)
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
