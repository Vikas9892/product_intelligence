import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/endpoints/pricing", () => ({ getPricingById: vi.fn() }));

import { getPricingById } from "@/lib/api/endpoints/pricing";
import { MetadataCard } from "@/features/product/metadata-card";
import { PricingCard } from "@/features/product/pricing-card";
import { ApiError } from "@/lib/api";
import type { ProductMeta } from "@/lib/api/product-metadata";

import { renderWithQuery } from "./test-utils";

const mockGetPricing = vi.mocked(getPricingById);

const META: ProductMeta = {
  name: "Blue Running Shoes",
  brand: "Nike",
  category: "shoes",
  price: 1999,
  description: "Lightweight",
  color: "blue",
  material: undefined,
  gender: undefined,
  season: undefined,
  style: undefined,
  tags: ["running", "breathable"],
  qualityScore: 0.8,
};

afterEach(() => vi.clearAllMocks());

describe("MetadataCard", () => {
  it("shows attributes and tags when metadata is present", () => {
    render(<MetadataCard meta={META} />);
    expect(screen.getByText("Color")).toBeInTheDocument();
    expect(screen.getByText("blue")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("Lightweight")).toBeInTheDocument();
  });

  it("explains the missing get-product endpoint when metadata is absent", () => {
    render(<MetadataCard meta={null} />);
    expect(screen.getByText(/no get-product endpoint/i)).toBeInTheDocument();
  });
});

describe("PricingCard", () => {
  it("renders the estimate and strategy", async () => {
    mockGetPricing.mockResolvedValue({
      estimated_price: 1899.5,
      confidence: "medium",
      confidence_score: 0.62,
      strategy: "trimmed_mean",
      comparable_count: 12,
      pricing_reason: "Estimated from 12 comparables.",
      comparables: [],
    });
    renderWithQuery(<PricingCard id="prod-1" />);

    expect(await screen.findByText("1,899.50")).toBeInTheDocument();
    expect(screen.getByText(/trimmed_mean/)).toBeInTheDocument();
  });

  it("shows a soft note when pricing is unavailable (404)", async () => {
    mockGetPricing.mockRejectedValue(new ApiError("nf", { status: 404, code: "HTTP_404" }));
    renderWithQuery(<PricingCard id="prod-1" />);

    expect(await screen.findByText(/isn't available for this product/i)).toBeInTheDocument();
  });
});
