import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";
import { env } from "@/config/env";
import { cn } from "@/lib/utils";

/**
 * Foundation smoke tests (Stage 3, Milestone 1).
 *
 * These verify the toolchain itself is wired correctly — the `@/*` path alias,
 * the JSX transform, jsdom + React Testing Library, the jest-dom matchers, the
 * `cn` class helper, and the typed env module. They are deliberately not
 * feature tests; those arrive with their features.
 */
describe("foundation", () => {
  it("cn merges and de-duplicates Tailwind classes", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", false, "font-bold")).toBe("text-sm font-bold");
  });

  it("env exposes sane, backend-free defaults", () => {
    // Same-origin by default: requests go through this app's rewrite proxy
    // (see next.config.ts), which is what makes them work against a stock
    // backend (CORS disabled) and lets the browser read its timing header.
    // An absolute NEXT_PUBLIC_API_BASE_URL opts out of the proxy.
    expect(env.apiBaseUrl === "" || /^https?:\/\//.test(env.apiBaseUrl)).toBe(true);
    expect(env.apiKeyHeader).toBe("X-API-Key");
    expect(env.apiPrefix.startsWith("/")).toBe(true);
  });

  it("renders a shadcn/ui primitive (RTL + jsdom + alias resolution work)", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });
});
