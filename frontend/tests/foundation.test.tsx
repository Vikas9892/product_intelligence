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
    expect(env.apiBaseUrl).toMatch(/^https?:\/\//);
    expect(env.apiKeyHeader).toBe("X-API-Key");
    expect(env.apiPrefix.startsWith("/")).toBe(true);
  });

  it("renders a shadcn/ui primitive (RTL + jsdom + alias resolution work)", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });
});
