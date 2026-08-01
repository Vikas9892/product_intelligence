import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api/client";
import { getTrends, TREND_GRANULARITIES, TREND_METRICS } from "@/lib/api/endpoints/analytics";

const TREND_RESPONSE = {
  metric: "search",
  granularity: "daily",
  points: [
    { period_start: "2026-07-31", value: 8.0 },
    { period_start: "2026-08-01", value: 2.0 },
  ],
  generated_at: "2026-08-01T13:40:05.942334Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("trend constants", () => {
  it("match the backend's AnalyticsEvent values", () => {
    // Mirrors backend/app/models/analytics_event.py — a mismatch here means the
    // UI would request a metric the backend rejects.
    expect([...TREND_METRICS]).toEqual(["upload", "search", "duplicate_check", "recommendation"]);
  });

  it("match the backend's TrendGranularity values", () => {
    expect([...TREND_GRANULARITIES]).toEqual(["daily", "weekly", "monthly"]);
  });
});

describe("getTrends", () => {
  it("builds the query string the backend expects", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: TREND_RESPONSE });

    await getTrends({ metric: "search", granularity: "weekly", periods: 30 });

    const url = get.mock.calls[0][0] as string;
    expect(url).toContain("/analytics/trends?");
    expect(url).toContain("metric=search");
    expect(url).toContain("granularity=weekly");
    expect(url).toContain("periods=30");
    // `format` is never sent — the UI only consumes JSON.
    expect(url).not.toContain("format=");
  });

  it("omits optional parameters so backend defaults apply", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: TREND_RESPONSE });

    await getTrends({ metric: "upload" });

    const url = get.mock.calls[0][0] as string;
    expect(url).toContain("metric=upload");
    expect(url).not.toContain("granularity=");
    expect(url).not.toContain("periods=");
  });

  it("returns the report body unchanged, zeros included", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { ...TREND_RESPONSE, points: [{ period_start: "2026-07-30", value: 0 }] },
    });

    const report = await getTrends({ metric: "search" });
    // A quiet day is real information; it must survive to the chart.
    expect(report.points).toEqual([{ period_start: "2026-07-30", value: 0 }]);
  });
});
