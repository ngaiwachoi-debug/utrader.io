"use client"

import { GoogleOAuthProvider } from "@react-oauth/google"
import { LanguageProvider } from "@/lib/i18n"

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? ""

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      {GOOGLE_CLIENT_ID ? (
        <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
          {children}
        </GoogleOAuthProvider>
      ) : (
        children
      )}
    </LanguageProvider>
  )
}
