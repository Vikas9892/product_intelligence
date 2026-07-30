import type { NextConfig } from "next";

/**
 * Next.js configuration.
 *
 * - `output: "standalone"` emits a self-contained server bundle under
 *   `.next/standalone`, which is what the later Docker/AWS deployment stages
 *   copy into a minimal Node image (no `node_modules` shipped separately).
 * - `reactStrictMode` surfaces unsafe lifecycles and side-effect bugs in dev.
 * - `images.remotePatterns` is intentionally empty for now; product image hosts
 *   are added when the image-serving strategy is finalized in a later stage.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  images: {
    remotePatterns: [],
  },
};

export default nextConfig;
