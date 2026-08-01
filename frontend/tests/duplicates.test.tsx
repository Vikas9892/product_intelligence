import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ComparisonView } from "@/features/duplicates/comparison-view";
import { CrossEncoderPanel, VerdictPanel } from "@/features/duplicates/verdict-panel";
import type { ProductMeta } from "@/lib/api/product-metadata";
import type { DuplicateCheckResponse } from "@/lib/api/types";

/** A real `POST /products/check-duplicate` response captured from the backend. */
const REAL_RESULT: DuplicateCheckResponse = {
  duplicate: true,
  confidence: 0.9888888888888889,
  reason: "Overall similarity 0.99 meets or exceeds the 0.90 threshold.",
  matched_product: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
  signals: {
    image: 1.0,
    text: 1.0,
    metadata: 0.9629629629629629,
    attribute: 0.9814814814814815,
  },
  top_candidates: [
    {
      product_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      image_similarity: 1.0,
      text_similarity: 1.0,
      metadata_similarity: 0.9629629629629629,
      attribute_similarity: 0.9814814814814815,
      overall_similarity: 0.9888888888888889,
    },
  ],
  // Null because DUPLICATE_VERIFICATION__ENABLED is off — the backend default.
  cross_encoder_score: null,
  retrieval_similarity: null,
  reasons: ["Overall similarity 0.99 meets or exceeds the 0.90 threshold."],
};

function withTooltip(ui: React.ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("VerdictPanel", () => {
  it("states the verdict in text, not colour alone, with confidence", () => {
    withTooltip(<VerdictPanel result={REAL_RESULT} />);
    expect(screen.getByText("Duplicate detected")).toBeInTheDocument();
    expect(screen.getByText(/High · 0\.99/)).toBeInTheDocument();
    expect(
      screen.getByText("Overall similarity 0.99 meets or exceeds the 0.90 threshold."),
    ).toBeInTheDocument();
  });

  it("reports a negative verdict distinctly", () => {
    withTooltip(<VerdictPanel result={{ ...REAL_RESULT, duplicate: false, confidence: 0.2 }} />);
    expect(screen.getByText("No duplicate detected")).toBeInTheDocument();
  });

  it("falls back to the single reason when the reasons list is empty", () => {
    withTooltip(<VerdictPanel result={{ ...REAL_RESULT, reasons: [] }} />);
    expect(
      screen.getByText("Overall similarity 0.99 meets or exceeds the 0.90 threshold."),
    ).toBeInTheDocument();
  });
});

describe("CrossEncoderPanel", () => {
  it("says the feature is disabled instead of showing a number when the score is null", () => {
    withTooltip(<CrossEncoderPanel result={REAL_RESULT} />);
    expect(screen.getByText("Disabled on this backend")).toBeInTheDocument();
    expect(screen.getByText(/DUPLICATE_VERIFICATION__ENABLED/)).toBeInTheDocument();
    expect(screen.queryByText("Cross-encoder score")).not.toBeInTheDocument();
  });

  it("shows the real scores when verification is enabled", () => {
    withTooltip(
      <CrossEncoderPanel
        result={{ ...REAL_RESULT, cross_encoder_score: 0.9612, retrieval_similarity: 0.8834 }}
      />,
    );
    expect(screen.getByText("0.9612")).toBeInTheDocument();
    expect(screen.getByText("0.8834")).toBeInTheDocument();
    expect(screen.queryByText("Disabled on this backend")).not.toBeInTheDocument();
  });

  it("renders a dash when only retrieval similarity is missing", () => {
    withTooltip(
      <CrossEncoderPanel
        result={{ ...REAL_RESULT, cross_encoder_score: 0.91, retrieval_similarity: null }}
      />,
    );
    expect(screen.getByText("0.9100")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

const submitted: ProductMeta = {
  name: "Blue Running Shoes",
  brand: "Nike",
  category: "Men Shoes",
  price: 1999,
  tags: [],
};

describe("ComparisonView", () => {
  it("marks matching and differing fields", () => {
    render(
      <ComparisonView
        submitted={submitted}
        submittedFile={null}
        matchedId="082c6d18"
        matchedMeta={{ ...submitted, price: 2049, tags: [] }}
        metadataLookupAttempted
      />,
    );
    // name/brand/category identical, price differs.
    expect(screen.getAllByText("Same").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Differs")).toBeInTheDocument();
  });

  it("treats two absent values as not comparable rather than as a match", () => {
    render(
      <ComparisonView
        submitted={{ name: "A", tags: [] }}
        submittedFile={null}
        matchedId="082c6d18"
        matchedMeta={{ name: "A", tags: [] }}
        metadataLookupAttempted
      />,
    );
    // Both sides lack brand/category/price/etc — claiming "Same" would
    // overstate evidence the backend never provided.
    expect(screen.getAllByText("Not comparable").length).toBeGreaterThan(0);
  });

  it("explains when the matched product's fields could not be resolved", () => {
    render(
      <ComparisonView
        submitted={submitted}
        submittedFile={null}
        matchedId="082c6d18"
        matchedMeta={null}
        metadataLookupAttempted
      />,
    );
    expect(screen.getByText(/could not be resolved/)).toBeInTheDocument();
  });

  it("says there is nothing to compare when no product matched", () => {
    render(
      <ComparisonView
        submitted={submitted}
        submittedFile={null}
        matchedId={null}
        matchedMeta={null}
        metadataLookupAttempted
      />,
    );
    expect(screen.getByText(/no matching product/)).toBeInTheDocument();
  });
});
