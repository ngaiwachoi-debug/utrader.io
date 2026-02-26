/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // Proxy API to backend so browser uses same origin (avoids CORS / "Cannot reach API server")
  async rewrites() {
    return [
      { source: "/api-backend/:path*", destination: "http://127.0.0.1:8000/:path*" },
    ];
  },
}

export default nextConfig
