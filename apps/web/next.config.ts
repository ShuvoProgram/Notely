import type { NextConfig } from "next";

// FastAPI is reached through a same-origin proxy so the HttpOnly session cookie is first-party.
const apiInternalUrl = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiInternalUrl}/api/:path*` },
      { source: "/health", destination: `${apiInternalUrl}/health` },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
