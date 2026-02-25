/**
 * Auth helpers for NextAuth session.
 * Backend token: fetch from /api/auth/token and send as Authorization: Bearer <token>
 */

let cachedBackendToken: string | null = null
let cacheExpiry = 0
const CACHE_MS = 5 * 60 * 1000 // 5 min

/** Get a JWT to send to the FastAPI backend (from NextAuth session). */
export async function getBackendToken(): Promise<string | null> {
  if (typeof window === "undefined") return null
  if (cachedBackendToken && Date.now() < cacheExpiry) {
    return cachedBackendToken
  }
  try {
    const res = await fetch("/api/auth/token", { credentials: "include" })
    if (!res.ok) return null
    const data = await res.json()
    const token = data.token ?? null
    if (token) {
      cachedBackendToken = token
      cacheExpiry = Date.now() + CACHE_MS
    } else {
      cachedBackendToken = null
    }
    return token
  } catch {
    return null
  }
}

/** Clear cached backend token (e.g. after sign out). */
export function clearBackendTokenCache(): void {
  cachedBackendToken = null
  cacheExpiry = 0
}

// Legacy keys for backward compat (NextAuth replaces these)
export const TOKEN_KEY = "utrader_id_token"

export function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  if (typeof window === "undefined") return
  localStorage.removeItem(TOKEN_KEY)
  clearBackendTokenCache()
}

/** Use useSession() from next-auth/react for signed-in state. */
export function isSignedIn(): boolean {
  return !!getToken()
}
