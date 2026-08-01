import type { NextConfig } from "next";

/**
 * Backend origin the proxy forwards to. Server-side only (not `NEXT_PUBLIC_*`)
 * because the browser never uses it directly — see the rewrite below.
 */
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

/**
 * Next.js configuration.
 *
 * - `output: "standalone"` emits a self-contained server bundle under
 *   `.next/standalone`, which is what the later Docker/AWS deployment stages
 *   copy into a minimal Node image (no `node_modules` shipped separately).
 * - `reactStrictMode` surfaces unsafe lifecycles and side-effect bugs in dev.
 * - `images.remotePatterns` is intentionally empty for now; product image hosts
 *   are added when the image-serving strategy is finalized in a later stage.
 * - `rewrites()` proxies the API — see below.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  images: {
    remotePatterns: [],
  },

  /**
   * Proxy the backend through this server so the browser talks to a **single
   * origin**. Two concrete reasons, both consequences of the backend being
   * frozen:
   *
   * 1. **CORS.** `APPLICATION__CORS_ALLOWED_ORIGINS` defaults to `[]`, so a
   *    direct `localhost:3000 -> localhost:8000` request is blocked outright.
   *    Proxying makes every request same-origin, so CORS never applies and the
   *    app works against a stock backend with no `.env` edits.
   * 2. **Response headers.** The backend stamps a real, server-measured
   *    `X-Response-Time-Ms` (see `backend/app/middleware/timing.py`), but
   *    `CORSMiddleware` is configured without `expose_headers`, so a
   *    cross-origin browser request could never read it. Same-origin responses
   *    expose every header, which is what lets the search workspace show
   *    genuine backend latency instead of a client-side guess.
   *
   * Setting `NEXT_PUBLIC_API_BASE_URL` to an absolute URL opts out (direct
   * cross-origin calls), which then requires backend CORS to be configured.
   */
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${BACKEND_ORIGIN}/api/v1/:path*` },
      { source: "/health", destination: `${BACKEND_ORIGIN}/health` },
      { source: "/ready", destination: `${BACKEND_ORIGIN}/ready` },
      { source: "/version", destination: `${BACKEND_ORIGIN}/version` },
    ];
  },
};

export default nextConfig;
