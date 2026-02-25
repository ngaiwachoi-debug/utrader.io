import { getToken } from "next-auth/jwt"
import { NextResponse } from "next/server"
import { SignJWT } from "jose"

const secret = process.env.NEXTAUTH_SECRET!
const encoder = new TextEncoder()

/**
 * Returns a backend-compatible JWT signed with NEXTAUTH_SECRET (sub, email).
 * Frontend sends this as Authorization: Bearer <token> to the FastAPI backend.
 */
export async function GET(request: Request) {
  const token = await getToken({
    req: request as unknown as { headers: Headers; url?: string },
    secret,
  })
  if (!token?.email) {
    return NextResponse.json({ token: null }, { status: 401 })
  }
  const payload = {
    sub: token.sub ?? token.id ?? token.email,
    email: token.email,
  }
  const jwt = await new SignJWT(payload)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("24h")
    .sign(encoder.encode(secret))
  return NextResponse.json({ token: jwt })
}
