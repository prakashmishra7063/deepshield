import type { NextConfig } from "next";

// The browser talks to the API through this same-origin proxy, so no CORS and
// signed report links work as plain downloads.
// Accepts a full URL or a bare host:port (as Render's private-network references provide).
const rawOrigin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
const API_ORIGIN = (/^https?:\/\//.test(rawOrigin) ? rawOrigin : `http://${rawOrigin}`).replace(/\/$/, "");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Uploads pass through the /api proxy; the API enforces the real limit (DS_MAX_UPLOAD_MB).
  experimental: { proxyClientMaxBodySize: "110mb" },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default config;
