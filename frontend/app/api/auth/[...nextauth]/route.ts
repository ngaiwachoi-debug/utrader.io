import NextAuth from "next-auth"
import GoogleProvider from "next-auth/providers/google"
import { UpstashRedisAdapter } from "@auth/upstash-redis-adapter"
import { Redis } from "@upstash/redis"

const redisUrl = process.env.UPSTASH_REDIS_REST_URL
const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN
const redis =
  redisUrl && redisToken
    ? new Redis({ url: redisUrl, token: redisToken })
    : null

const handler = NextAuth({
  ...(redis && { adapter: UpstashRedisAdapter(redis) }),
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    signIn: async ({ user }) => {
      if (!user.email || !user.email.endsWith("@gmail.com")) {
        return false
      }
      return true
    },
    jwt: async ({ token, user }) => {
      if (user?.id) token.id = user.id
      if (user?.email) token.email = user.email
      return token
    },
    session: async ({ session, token }) => {
      if (session.user) {
        const u = session.user as { id?: string; email?: string }
        u.id = String(token.sub ?? token.id ?? "")
        u.email = String(token.email ?? "")
      }
      return session
    },
  },
  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60,
  },
  pages: {
    signIn: "/login",
  },
  theme: {
    colorScheme: "dark",
    brandColor: "#10b981",
  },
  secret: process.env.NEXTAUTH_SECRET,
})

export { handler as GET, handler as POST }
