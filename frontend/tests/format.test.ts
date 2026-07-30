import { describe, expect, it } from "vitest";

import { formatDate, formatNumber, formatPercent, formatPrice, formatScore } from "@/lib/format";

describe("format utilities", () => {
  it("formatNumber groups thousands", () => {
    expect(formatNumber(12345)).toBe("12,345");
  });

  it("formatPrice keeps two decimals", () => {
    expect(formatPrice(1899.5)).toBe("1,899.50");
    expect(formatPrice(1999)).toBe("1,999.00");
  });

  it("formatPercent renders a whole percent from a ratio", () => {
    expect(formatPercent(0.83)).toBe("83%");
    expect(formatPercent(0.5, 1)).toBe("50.0%");
  });

  it("formatScore fixes precision", () => {
    expect(formatScore(0.8312)).toBe("0.83");
    expect(formatScore(0.8, 3)).toBe("0.800");
  });

  it("formatDate accepts an ISO string and a Date", () => {
    // Locale-independent assertion: both inputs produce the same output and
    // reference the correct year.
    const iso = "2026-07-24T10:00:00Z";
    expect(formatDate(iso)).toBe(formatDate(new Date(iso)));
    expect(formatDate(iso)).toContain("2026");
  });
});
