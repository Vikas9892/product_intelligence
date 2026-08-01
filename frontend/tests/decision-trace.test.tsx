import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DecisionTrace } from "@/features/explanations/decision-trace";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ExplanationResponse } from "@/lib/api/types";

/**
 * A real `GET /products/{id}/explanations` recommendation trace, copied from a
 * live backend response. Note the contributions (0.9998 + 0.6944 = 1.694) do
 * NOT sum to `total` (0.9693) — the scorer applies its own configured weights
 * internally. The UI must not present the total as a sum.
 */
const REAL_TRACE: ExplanationResponse = {
  decision_type: "recommendation",
  subject_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
  summary:
    "Recommended because it shares: the same brand, the same category, matching color, material, gender, style.",
  confidence: 0.9693148348893941,
  reasons: [
    { code: "shared_brand", description: "the same brand", weight: null },
    { code: "shared_category", description: "the same category", weight: null },
    {
      code: "matched_attributes",
      description: "matching color, material, gender, style",
      weight: null,
    },
  ],
  breakdown: {
    components: [
      { name: "similarity", value: 0.999773529, weight: 1.0, contribution: 0.999773529 },
      { name: "quality", value: 0.6943939393939393, weight: 1.0, contribution: 0.6943939393939393 },
    ],
    total: 0.9693148348893941,
  },
  created_at: "2026-07-31T03:13:22.570813Z",
};

function renderTrace(explanation: ExplanationResponse) {
  return render(
    <TooltipProvider>
      <DecisionTrace explanation={explanation} />
    </TooltipProvider>,
  );
}

describe("DecisionTrace", () => {
  it("renders the backend's own summary and confidence", () => {
    renderTrace(REAL_TRACE);
    expect(screen.getByText(/Recommended because it shares/)).toBeInTheDocument();
    // ConfidenceBadge shows level + score.
    expect(screen.getByText(/High · 0\.97/)).toBeInTheDocument();
  });

  it("lists every reason code the backend returned", () => {
    renderTrace(REAL_TRACE);
    expect(screen.getByText("Same brand")).toBeInTheDocument();
    expect(screen.getByText("Same category")).toBeInTheDocument();
    expect(screen.getByText("Matching attributes")).toBeInTheDocument();
    expect(screen.getByText("the same brand")).toBeInTheDocument();
  });

  it("shows each component's value, weight, and contribution as reported", () => {
    renderTrace(REAL_TRACE);
    expect(screen.getByText("similarity")).toBeInTheDocument();
    expect(screen.getByText("quality")).toBeInTheDocument();
    expect(
      screen.getByText(/value 1\.00 · weight 1\.00 ·\s*contribution 1\.00/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/value 0\.69 · weight 1\.00 ·\s*contribution 0\.69/),
    ).toBeInTheDocument();
  });

  it("presents the total as the backend's final score, not a sum of contributions", () => {
    renderTrace(REAL_TRACE);
    // 0.97, the reported total — not 1.69, which is what summing would give.
    expect(screen.getByText("Final 0.97")).toBeInTheDocument();
    expect(screen.queryByText(/1\.69/)).not.toBeInTheDocument();
  });

  it("falls back to the raw code when a reason code has no friendly label", () => {
    renderTrace({
      ...REAL_TRACE,
      reasons: [{ code: "some_future_code", description: "described by the backend", weight: 0.4 }],
      breakdown: null,
    });
    expect(screen.getByText("some_future_code")).toBeInTheDocument();
    expect(screen.getByText("described by the backend")).toBeInTheDocument();
    expect(screen.getByText("(weight 0.40)")).toBeInTheDocument();
  });

  it("omits the breakdown entirely when the backend reports none", () => {
    renderTrace({ ...REAL_TRACE, breakdown: null, confidence: null });
    expect(screen.queryByText("Score components")).not.toBeInTheDocument();
    expect(screen.queryByText(/Final /)).not.toBeInTheDocument();
  });
});
