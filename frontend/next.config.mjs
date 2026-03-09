import createNextIntlPlugin from "next-intl/plugin"

const withNextIntl = createNextIntlPlugin("./i18n/request.ts")

/** @type {import('next').NextConfig} */
const nextConfig = { typescript: { ignoreBuildErrors: true }, eslint: { ignoreDuringBuilds: true },
  typescript: {
    ignoreBuildErrors: process.env.NODE_ENV !== "production",
  },
  images: {
    unoptimized: true,
  },
  // Proxy API to backend so browser uses same origin (avoids CORS). Backend must run on BACKEND_PORT (default 8000).
  async rewrites() {
    const port = process.env.BACKEND_PORT || "8000"
    return {
      fallback: [
        { source: "/api-backend/:path*", destination: `http://127.0.0.1:${port}/:path*` },
      ],
    };
  },
}

export default withNextIntl(nextConfig)
