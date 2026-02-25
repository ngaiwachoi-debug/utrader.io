"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { GoogleLogin } from "@react-oauth/google"
import { setToken } from "@/lib/auth"
import { useT } from "@/lib/i18n"

export default function LoginPage() {
  const router = useRouter()
  const t = useT()
  const [token, setTokenInput] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [showDevForm, setShowDevForm] = useState(false)

  const handleGoogleSuccess = (credentialResponse: { credential?: string }) => {
    const idToken = credentialResponse.credential
    if (!idToken) {
      setError("No credential returned.")
      return
    }
    setToken(idToken)
    router.push("/dashboard")
    router.refresh()
  }

  const handleDevSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const trimmed = token.trim()
    if (!trimmed) {
      setError("Please enter your Google ID token.")
      return
    }
    try {
      setToken(trimmed)
      router.push("/dashboard")
      router.refresh()
    } catch {
      setError("Could not save token.")
    }
  }

  const hasGoogleClientId = typeof process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID === "string" && process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID.length > 0

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-lg">
        <div className="flex items-center gap-2 mb-8">
          <span className="text-xl font-semibold text-foreground">
            uTrader<span className="text-emerald">.io</span>
          </span>
        </div>

        <h1 className="text-2xl font-bold text-foreground mb-2">{t("login.signIn")}</h1>
        <p className="text-sm text-muted-foreground mb-6">
          {t("login.continueWithGoogle")} — {t("login.freeToUse")}, {t("login.secureOAuth")}, {t("login.noDataStored")}.
        </p>

        {hasGoogleClientId ? (
          <>
            <div className="flex justify-center mb-6">
              <GoogleLogin
                onSuccess={handleGoogleSuccess}
                onError={() => setError("Google sign-in failed.")}
                theme="filled_black"
                size="large"
                text="continue_with"
                shape="rectangular"
                width="320"
              />
            </div>
            <p className="text-center text-xs text-muted-foreground mb-4">
              <button
                type="button"
                onClick={() => setShowDevForm(true)}
                className="text-emerald hover:underline"
              >
                Developer: paste ID token instead
              </button>
            </p>
          </>
        ) : null}

        {(showDevForm || !hasGoogleClientId) && (
          <form onSubmit={handleDevSubmit} className="flex flex-col gap-4 border-t border-border pt-6">
            <div>
              <label className="text-sm font-medium text-foreground block mb-1.5">Google ID Token</label>
              <textarea
                value={token}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Paste your Google ID token here"
                rows={3}
                className="w-full rounded-lg border border-border bg-secondary px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-emerald/50 focus:ring-1 focus:ring-emerald/50 font-mono"
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <button
              type="submit"
              className="rounded-lg bg-emerald px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-emerald/90 transition-colors"
            >
              Sign in and go to Dashboard
            </button>
          </form>
        )}

        <p className="mt-6 text-xs text-muted-foreground text-center">
          <Link href="/dashboard" className="text-emerald hover:underline">
            {t("login.backToDashboard")} →
          </Link>
        </p>
      </div>
    </div>
  )
}
