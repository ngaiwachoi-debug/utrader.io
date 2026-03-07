import NextAuth, { NextAuthOptions } from "next-auth"
import GoogleProvider from "next-auth/providers/google"
import { UpstashRedisAdapter } from "@auth/upstash-redis-adapter"
import { Redis } from "@upstash/redis"

const envUrl = process.env.UPSTASH_REDIS_REST_URL ?? process.env.REDIS_URL
const redisUrl = envUrl?.startsWith("http") ? envUrl : undefined
const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN
const redis =
  redisUrl && redisToken
    ? new Redis({ url: redisUrl, token: redisToken })
    : null

export const authOptions: NextAuthOptions = {
  ...(redis && { adapter: UpstashRedisAdapter(redis) }),
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    async signIn({ user }) {
      if (user.email && user.email.endsWith("@gmail.com")) {
        return true
      }
      return "/?error=AccessDenied"
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as { id?: string }).id = token.sub ?? (token as { id?: string }).id
      }
      return session
    },
  },
  session: { strategy: "jwt", maxAge: 30 * 24 * 60 * 60 },
  pages: {
    signIn: "/",
  },
  theme: {
    colorScheme: "dark",
    brandColor: "#10b981",
  },
  secret: (process.env.NEXTAUTH_SECRET || "").trim() || undefined,
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }