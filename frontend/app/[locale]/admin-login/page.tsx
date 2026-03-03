"use client"

import { useEffect } from "react"
import { signIn, useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useParams } from "next/navigation"

export default function AdminLoginPage() {
  const params = useParams()
  const locale = (params?.locale as string) || "en"
  const { data: session, status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (status === "authenticated" && session?.user) {
      router.replace(`/${locale}/admin`)
    }
  }, [status, session, router, locale])

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-lg">
        <div className="flex items-center gap-2 mb-8">
          <span className="text-xl font-semibold text-foreground">
            bifinexbot<span className="text-primary">.com</span> Admin
          </span>
        </div>

        <h1 className="text-2xl font-bold text-foreground mb-2">Admin login</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Sign in with Google. Only the configured admin email (ngaiwachoi@gmail.com) can access the admin panel.
        </p>

        <button
          type="button"
          onClick={() => signIn("google", { callbackUrl: `/${locale}/admin` })}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-base font-semibold text-white hover:bg-primary/90 transition-colors border-0"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24">
            <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Sign in with Google
        </button>

        <p className="mt-6 text-xs text-muted-foreground text-center">
          <Link href={`/${locale}`} className="text-primary hover:underline">
            ← Back to home
          </Link>
        </p>
      </div>
    </div>
  )
}
