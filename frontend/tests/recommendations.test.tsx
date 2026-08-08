import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_RECOMMENDATION_FILTERS,
  filterRecommendations,
  overlapSummary,
  sortRecommendations,
} from "@/features/recommendations/filtering";
import { RecommendationCard } from "@/features/recommendations/recommendation-card";
import type { RecommendationInfo } from "@/lib/api/types";

/** Shaped exactly like a live `GET /products/{id}/recommendations` entry. */
function rec(
  id: string,
  score: number,
  overrides: Partial<RecommendationInfo["reason"]> = {},
  explanation = "Similar visual appearance.",
): RecommendationInfo {
  return {
    product_id: id,
    score,
    reason: {
      matched_attributes: [],
      matched_tags: [],
      shared_brand: false,
      shared_category: false,
      ...overrides,
    },
    explanation,
  };
}

const STRONG = rec(
  "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
  0.9693148348893941,
  {
    matched_attributes: ["color", "material", "gender", "style"],
    matched_tags: ["blue", "mesh", "nike", "running"],
    shared_brand: true,
    shared_category: true,
  },
  "Similar visual appearance; same category; same brand; shared attributes (color, material).",
);

const WEAK = rec("b926f921-5b1d-45eb-8320-67cab7f4e9d5", 0.5297858656768398, {
  matched_tags: ["bright", "square"],
});

const items = [STRONG, WEAK];

describe("filterRecommendations", () => {
  it("returns everything by default", () => {
    expect(filterRecommendations(items, DEFAULT_RECOMMENDATION_FILTERS)).toHaveLength(2);
  });

  it("filters on shared brand and category", () => {
    const brand = filterRecommendations(items, {
      ...DEFAULT_RECOMMENDATION_FILTERS,
      sharedBrand: true,
    });
    expect(brand.map((r) => r.product_id)).toEqual([STRONG.product_id]);

    const category = filterRecommendations(items, {
      ...DEFAULT_RECOMMENDATION_FILTERS,
      sharedCategory: true,
    });
    expect(category.map((r) => r.product_id)).toEqual([STRONG.product_id]);
  });

  it("filters on having matched attributes", () => {
    const withAttrs = filterRecommendations(items, {
      ...DEFAULT_RECOMMENDATION_FILTERS,
      hasAttributes: true,
    });
    expect(withAttrs.map((r) => r.product_id)).toEqual([STRONG.product_id]);
  });

  it("applies the minimum score", () => {
    expect(
      filterRecommendations(items, { ...DEFAULT_RECOMMENDATION_FILTERS, minScore: 0.75 }),
    ).toHaveLength(1);
    expect(
      filterRecommendations(items, { ...DEFAULT_RECOMMENDATION_FILTERS, minScore: 0.99 }),
    ).toHaveLength(0);
  });

  it("combines filters conjunctively", () => {
    expect(
      filterRecommendations(items, {
        sharedBrand: true,
        sharedCategory: true,
        hasAttributes: true,
        minScore: 0.9,
      }),
    ).toHaveLength(1);
  });
});

describe("sortRecommendations", () => {
  it("sorts by score, descending by default direction", () => {
    const sorted = sortRecommendations(items, "score", "desc");
    expect(sorted.map((r) => r.product_id)).toEqual([STRONG.product_id, WEAK.product_id]);
    const asc = sortRecommendations(items, "score", "asc");
    expect(asc.map((r) => r.product_id)).toEqual([WEAK.product_id, STRONG.product_id]);
  });

  it("sorts by matched attribute and tag counts", () => {
    expect(sortRecommendations(items, "attributes", "desc")[0].product_id).toBe(STRONG.product_id);
    expect(sortRecommendations(items, "tags", "desc")[0].product_id).toBe(STRONG.product_id);
  });

  it("does not mutate the input", () => {
    const original = [...items];
    sortRecommendations(items, "score", "asc");
    expect(items).toEqual(original);
  });
});

describe("overlapSummary", () => {
  it("counts each overlap kind across the set", () => {
    expect(overlapSummary(items)).toEqual({
      sharedBrand: 1,
      sharedCategory: 1,
      withAttributes: 1,
    });
  });
});

describe("RecommendationCard", () => {
  it("renders the backend's own explanation and score", () => {
    render(<RecommendationCard recommendation={STRONG} rank={1} />);
    expect(screen.getByText(/Similar visual appearance; same category/)).toBeInTheDocument();
    expect(screen.getByText(/High · 0\.97/)).toBeInTheDocument();
  });

  it("shows matched attributes and tags with their counts", () => {
    render(<RecommendationCard recommendation={STRONG} rank={1} />);
    expect(screen.getByText("Matched attributes (4)")).toBeInTheDocument();
    expect(screen.getByText("Matched tags (4)")).toBeInTheDocument();
    expect(screen.getByText("color")).toBeInTheDocument();
    expect(screen.getByText("nike")).toBeInTheDocument();
  });

  it("shows brand/category overlap as present or absent, never omitted", () => {
    render(<RecommendationCard recommendation={WEAK} rank={2} />);
    // Both chips render even when false, so "not shared" is distinguishable
    // from "not reported".
    expect(screen.getByText("Same brand")).toBeInTheDocument();
    expect(screen.getByText("Same category")).toBeInTheDocument();
  });

  it("distinguishes loading, failed, not-found and unnamed instead of one placeholder", () => {
    // Regression: all three previously rendered as "Unresolved product", which
    // told a reader nothing about which state they were actually looking at.
    const { rerender } = render(
      <RecommendationCard recommendation={WEAK} rank={2} resolutionState="loading" />,
    );
    expect(screen.getByText("Loading product…")).toBeInTheDocument();

    rerender(<RecommendationCard recommendation={WEAK} rank={2} resolutionState="missing" />);
    expect(screen.getByText("Product not found")).toBeInTheDocument();

    rerender(<RecommendationCard recommendation={WEAK} rank={2} resolutionState="failed" />);
    expect(screen.getByText("Couldn't load this product")).toBeInTheDocument();

    rerender(<RecommendationCard recommendation={WEAK} rank={2} resolutionState="resolved" />);
    expect(screen.getByText("Product has no name")).toBeInTheDocument();

    // The id stays visible throughout, so a card is always identifiable.
    expect(screen.getByText(WEAK.product_id)).toBeInTheDocument();
  });

  it("renders the resolved product name, not a placeholder", () => {
    render(
      <RecommendationCard
        recommendation={WEAK}
        rank={2}
        meta={{ name: "Demo Trailblazer Trail Shoe Black", tags: [] }}
      />,
    );

    expect(screen.getByText("Demo Trailblazer Trail Shoe Black")).toBeInTheDocument();
    expect(screen.queryByText("Unresolved product")).not.toBeInTheDocument();
    expect(screen.queryByText("Product not found")).not.toBeInTheDocument();
  });

  it("uses resolved metadata when available", () => {
    render(
      <RecommendationCard
        recommendation={WEAK}
        rank={2}
        meta={{ name: "Red Ceramic Mug", brand: "Corelle", price: 499, tags: [] }}
      />,
    );
    expect(screen.getByText("Red Ceramic Mug")).toBeInTheDocument();
    expect(screen.getByText("Corelle")).toBeInTheDocument();
  });

  it("says so when a recommendation rests on embedding similarity alone", () => {
    render(<RecommendationCard recommendation={rec("x", 0.4)} rank={3} />);
    expect(screen.getByText(/embedding similarity alone/)).toBeInTheDocument();
  });
});
