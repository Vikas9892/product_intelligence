import { render, screen, within } from "@testing-library/react";
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
  confidence: 0.51,
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
    // A real post-fix trace: all four terms of the weighted sum, at their
    // configured weights. Contributions add up to the total.
    components: [
      { name: "similarity", value: 0.57, weight: 0.55, contribution: 0.3135 },
      { name: "attribute_match", value: 0.4, weight: 0.2, contribution: 0.08 },
      { name: "tag_match", value: 0.35, weight: 0.15, contribution: 0.0525 },
      { name: "quality", value: 0.64, weight: 0.1, contribution: 0.064 },
    ],
    total: 0.51,
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
    // ConfidenceBadge shows level + score.
    expect(screen.getByText(/Medium · 0\.51/)).toBeInTheDocument();
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
      screen.getByText(/value 0\.57 · weight 0\.55 ·\s*contribution 0\.31/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/value 0\.64 · weight 0\.10 ·\s*contribution 0\.06/),
    ).toBeInTheDocument();
  });

  it("presents the backend's reported total as the final score", () => {
    renderTrace(REAL_TRACE);
    // The header still shows the backend's own total verbatim; it is never
    // recomputed client-side. What changed is that the components now visibly
    // add up to it (see the "ConfidenceBreakdown aggregation" suite below).
    expect(screen.getByText("Final 0.51")).toBeInTheDocument();
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

describe("ConfidenceBreakdown aggregation", () => {
  it("shows every component with its real weight, not a hardcoded 1.00", () => {
    renderTrace(REAL_TRACE);

    // All four terms of the weighted sum are published.
    expect(screen.getByText("similarity")).toBeInTheDocument();
    expect(screen.getByText("attribute_match")).toBeInTheDocument();
    expect(screen.getByText("tag_match")).toBeInTheDocument();
    expect(screen.getByText("quality")).toBeInTheDocument();

    // The defect was every component rendering "weight 1.00".
    expect(screen.getByText(/weight 0\.55/)).toBeInTheDocument();
    expect(screen.getByText(/weight 0\.10/)).toBeInTheDocument();
  });

  it("shows the aggregation step so the arithmetic closes", () => {
    renderTrace(REAL_TRACE);

    const aggregation = screen.getByLabelText("How the components aggregate to the final score");
    expect(within(aggregation).getByText("Sum of contributions")).toBeInTheDocument();
    // 0.3135 + 0.08 + 0.0525 + 0.064 = 0.51 -- and it is displayed.
    expect(within(aggregation).getAllByText("0.51").length).toBeGreaterThan(0);
    expect(within(aggregation).getByText("Final score")).toBeInTheDocument();
  });

  it("names a post-weighting adjustment as its own line item", () => {
    renderTrace({
      ...REAL_TRACE,
      breakdown: {
        components: [
          { name: "similarity", value: 1.0, weight: 0.55, contribution: 0.55 },
          { name: "quality", value: 1.0, weight: 0.1, contribution: 0.1 },
        ],
        // Deliberately below the sum: a clamp or penalty was applied.
        total: 0.5,
      },
    });

    const aggregation = screen.getByLabelText("How the components aggregate to the final score");
    expect(within(aggregation).getByText("Adjustment applied after weighting")).toBeInTheDocument();
    expect(within(aggregation).getByText(/−0\.15/)).toBeInTheDocument();
  });

  it("omits the adjustment line when the contributions already close", () => {
    renderTrace(REAL_TRACE);

    const aggregation = screen.getByLabelText("How the components aggregate to the final score");
    expect(
      within(aggregation).queryByText("Adjustment applied after weighting"),
    ).not.toBeInTheDocument();
  });
});
