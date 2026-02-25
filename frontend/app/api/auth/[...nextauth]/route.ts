import NextAuth, { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import { UpstashRedisAdapter } from "@next-auth/upstash-redis-adapter";
import { Redis } from "@upstash/redis";

const redis = new Redis({
  url: process.env.REDIS_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!, // Make sure this is in .env or use the full URL logic
});

export const authOptions: NextAuthOptions = {
  adapter: UpstashRedisAdapter(redis),
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    async signIn({ user }) {
      if (user.email && user.email.endsWith("@gmail.com")) {
        return true;
      }
      return "/?error=AccessDenied"; // Redirects to login page with error
    },
    async session({ session, user }) {
      if (session.user) {
        session.user.id = user.id; // Pass user ID to frontend
      }
      return session;
    },
  },
  pages: {
    signIn: "/", // Custom login page (your landing page)
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };