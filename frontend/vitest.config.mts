import react from "@vitejs/plugin-react-swc";
import tsconfigPaths from "vite-tsconfig-paths";
import { defineConfig } from "vitest/config";

/**
 * Vitest configuration.
 *
 * - `@vitejs/plugin-react-swc` provides the JSX/TSX transform (SWC-based, so it
 *   avoids the Babel toolchain and its peer-dependency conflicts).
 * - `vite-tsconfig-paths` makes the `@/*` alias resolve in tests exactly as it
 *   does in the app.
 * - jsdom + a shared setup file give React Testing Library a DOM and the
 *   jest-dom matchers.
 */
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}", "tests/**/*.{test,spec}.{ts,tsx}"],
  },
});
