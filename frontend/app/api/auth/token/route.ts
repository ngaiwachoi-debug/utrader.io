import { getToken } from "next-auth/jwt"
import { NextRequest, NextResponse } from "next/server"
import { SignJWT } from "jose"

const encoder = new TextEncoder()

/**
 * Returns a backend-compatible JWT signed with NEXTAUTH_SECRET (sub, email).
 * Frontend sends this as Authorization: Bearer <token> to the FastAPI backend.
 */
export async function GET(request: NextRequest) {
  const rawSecret = process.env.NEXTAUTH_SECRET
  const secret = typeof rawSecret === "string" ? rawSecret.trim() : ""
  if (!secret) {
    return NextResponse.json(
      { error: "NEXTAUTH_SECRET not set. Add it to frontend/.env.local (same value as root .env)." },
      { status: 500 }
    )
  }
  const token = await getToken({
    req: request,
    secret,
  })
  if (!token?.email) {
    return NextResponse.json({ token: null }, { status: 401 })
  }
  const payload = {
    sub: String(token.sub || "") ?? token.id ?? token.email,
    email: token.email,
  }
  const jwt = await new SignJWT(payload)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("24h")
    .sign(encoder.encode(secret))
  return NextResponse.json({ token: jwt })
}
