import type { NextConfig } from "next";

// FastAPI is reached through a same-origin proxy so the HttpOnly session cookie is first-party.
const apiInternalUrl = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");
// HSTS/upgrade-insecure-requests only make sense behind TLS; opt in explicitly per deployment.
const isProduction = process.env.WEB_SECURE === "true";

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
    // Next.js needs inline scripts for hydration, hence 'unsafe-inline' on script-src; everything
    // else is locked to this origin. The API responses carry their own (stricter) headers.
    const csp = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data:",
      "connect-src 'self'",
      "frame-ancestors 'none'",
      "form-action 'self'",
      "base-uri 'self'",
      "object-src 'none'",
      ...(isProduction ? ["upgrade-insecure-requests"] : []),
    ].join("; ");
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          ...(isProduction ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }] : []),
        ],
      },
    ];
  },
};

export default nextConfig;
