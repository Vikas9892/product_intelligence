/**
 * Global test setup, loaded once before the suite (see `vitest.config.ts`).
 *
 * - Registers `@testing-library/jest-dom` matchers (e.g. `toBeInTheDocument`).
 * - Registers `jest-axe`'s `toHaveNoViolations` for accessibility assertions.
 * - Polyfills `matchMedia`, which jsdom does not implement but responsive
 *   components (the sidebar's mobile hook) rely on.
 */
import "@testing-library/jest-dom/vitest";
import { toHaveNoViolations } from "jest-axe";
import { expect, vi } from "vitest";

expect.extend(toHaveNoViolations);

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
