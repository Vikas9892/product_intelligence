import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { EstimateSummary, OutlierNote } from "@/features/pricing/estimate-summary";
import { computeSpread, toDistributionData } from "@/features/pricing/spread";
import type { PricingResponse } from "@/lib/api/types";

/** A real `POST /pricing/estimate` response captured from the backend. */
const REAL_RESULT: PricingResponse = {
  estimated_price: 1515.67,
  confidence: "low",
  confidence_score: 0.263,
  strategy: "trimmed_mean",
  comparable_count: 3,
  pricing_reason:
    "Estimated from 3 comparable product(s) using the trimmed_mean strategy (low confidence).",
  comparables: [
    {
      product_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      price: 2049.0,
      similarity: 0.9521787,
      name: "Blue Running Shoes",
      brand: "Nike",
      category: "men-shoes",
    },
    {
      product_id: "ac36cc32-706f-4874-95ad-0ca9bb076d7f",
      price: 1999.0,
      similarity: 0.9521787,
      name: "Blue Running Shoes",
      brand: "Nike",
      category: "men-shoes",
    },
    {
      product_id: "b926f921-5b1d-45eb-8320-67cab7f4e9d5",
      price: 499.0,
      similarity: 0.4222116,
      name: "Red Ceramic Mug",
      brand: "Corelle",
      category: "kitchenware",
    },
  ],
};

function withTooltip(ui: React.ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("computeSpread", () => {
  it("summarizes the returned comparables", () => {
    const spread = computeSpread(REAL_RESULT.comparables ?? [], REAL_RESULT.estimated_price);
    expect(spread).not.toBeNull();
    expect(spread!.count).toBe(3);
    expect(spread!.min).toBe(499);
    expect(spread!.median).toBe(1999);
    expect(spread!.max).toBe(2049);
  });

  it("averages the middle pair for an even count", () => {
    const spread = computeSpread(
      [
        { product_id: "a", price: 100, similarity: 1 },
        { product_id: "b", price: 200, similarity: 1 },
      ],
      150,
    );
    expect(spread!.median).toBe(150);
  });

  it("returns null when there is nothing to summarize", () => {
    expect(computeSpread([], 0)).toBeNull();
  });

  it("reports no estimate position when every price is identical", () => {
    const spread = computeSpread(
      [
        { product_id: "a", price: 500, similarity: 1 },
        { product_id: "b", price: 500, similarity: 1 },
      ],
      500,
    );
    expect(spread!.estimatePosition).toBeNull();
  });
});

describe("toDistributionData", () => {
  it("sorts cheapest first and labels by name", () => {
    const data = toDistributionData(REAL_RESULT.comparables ?? []);
    expect(data.map((d) => d.price)).toEqual([499, 1999, 2049]);
    expect(data[0].label).toBe("Red Ceramic Mug");
  });

  it("falls back to a shortened id when a comparable has no name", () => {
    const data = toDistributionData([
      { product_id: "abcdef1234567890", price: 10, similarity: 0.5 },
    ]);
    expect(data[0].label).toBe("abcdef12…");
  });
});

describe("EstimateSummary", () => {
  it("renders the backend's estimate, confidence, strategy, and reason verbatim", () => {
    withTooltip(<EstimateSummary result={REAL_RESULT} />);
    expect(screen.getByText("1,515.67")).toBeInTheDocument();
    expect(screen.getByText(/Low · 0\.26/)).toBeInTheDocument();
    expect(screen.getByText("trimmed_mean")).toBeInTheDocument();
    expect(screen.getByText(/Estimated from 3 comparable/)).toBeInTheDocument();
  });

  it("labels the spread as locally computed so it cannot read as a backend figure", () => {
    withTooltip(<EstimateSummary result={REAL_RESULT} />);
    expect(screen.getByText(/computed here for context/)).toBeInTheDocument();
    expect(screen.getByText(/The estimate above is the backend's\./)).toBeInTheDocument();
  });

  it("says a zero estimate with no comparables is not a real valuation", () => {
    withTooltip(
      <EstimateSummary
        result={{
          ...REAL_RESULT,
          estimated_price: 0,
          comparable_count: 0,
          comparables: [],
          pricing_reason: "No priced comparables were found.",
        }}
      />,
    );
    expect(screen.getByText(/not a real valuation/)).toBeInTheDocument();
  });
});

describe("OutlierNote", () => {
  it("explains that outliers were removed server-side and are absent from the payload", () => {
    render(<OutlierNote result={REAL_RESULT} />);
    expect(screen.getByText(/Tukey IQR fence/)).toBeInTheDocument();
    expect(screen.getByText(/are not part of the response/)).toBeInTheDocument();
    // And that no client-side detection is attempted.
    expect(screen.getByText(/no outlier detection is re-run in the browser/)).toBeInTheDocument();
  });

  it("surfaces a mismatch between the reported count and what was returned", () => {
    render(<OutlierNote result={{ ...REAL_RESULT, comparable_count: 5 }} />);
    expect(screen.getByText(/reports 5 used against 3 returned/)).toBeInTheDocument();
  });
});
