import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/endpoints/analytics", () => ({
  getDashboard: vi.fn(),
  getPipelineReport: vi.fn(),
  getModelAnalytics: vi.fn(),
}));

import { getDashboard } from "@/lib/api/endpoints/analytics";
import { ApiError } from "@/lib/api";
import { MetricsCards } from "@/features/dashboard/metrics-cards";

import { renderWithQuery } from "./test-utils";

const mockGetDashboard = vi.mocked(getDashboard);

const FIXTURE = {
  today: {
    uploads: 12,
    searches: 40,
    duplicate_checks: 3,
    recommendations: 8,
    average_processing_seconds: 1.23,
  },
  window: {
    uploads: 100,
    searches: 300,
    duplicate_checks: 20,
    recommendations: 60,
    average_processing_seconds: 1.5,
  },
  window_days: 7,
  active_models: 3,
  generated_at: "2026-07-24T00:00:00Z",
};

beforeEach(() => {
  mockGetDashboard.mockReset();
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("Dashboard metrics", () => {
  it("renders real metric values from the backend response", async () => {
    mockGetDashboard.mockResolvedValue(FIXTURE);
    renderWithQuery(<MetricsCards />);

    expect(await screen.findByText("Uploads today")).toBeInTheDocument();
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("1.23s")).toBeInTheDocument();
  });

  it("shows an error state with retry when the request fails", async () => {
    mockGetDashboard.mockRejectedValue(new ApiError("boom", { status: 500, code: "X" }));
    renderWithQuery(<MetricsCards />);

    expect(await screen.findByText("Couldn't load metrics")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
