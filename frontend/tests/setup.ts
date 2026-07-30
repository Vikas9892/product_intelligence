/**
 * Global test setup, loaded once before the suite (see `vitest.config.ts`).
 *
 * Registers the `@testing-library/jest-dom` matchers (e.g. `toBeInTheDocument`)
 * on Vitest's `expect`, and polyfills `matchMedia`, which jsdom does not
 * implement but responsive components (the sidebar's mobile hook) rely on.
 */
import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
