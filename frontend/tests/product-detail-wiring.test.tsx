import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const PRODUCT_ID = "9a0b9df2-f9e1-453d-8e63-11ae6502d7f5";
const REC_ID = "41b98c4e-c43a-4bf5-aaba-6e4f25b8657c";

vi.mock("@/lib/api/endpoints/products", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/endpoints/products")>()),
  getRecommendations: vi.fn(async () => ({
    product_id: PRODUCT_ID,
    recommendation_type: "similar",
    recommendations: [
      {
        product_id: REC_ID,
        score: 0.96,
        reason: {
          matched_attributes: ["color"],
          matched_tags: ["running"],
          shared_brand: false,
          shared_category: true,
        },
        explanation: "Similar visual appearance",
      },
    ],
    generated_at: "2026-08-08T00:00:00Z",
  })),
  getProductsBatch: vi.fn(async () => ({
    products: [
      {
        product_id: REC_ID,
        name: "Demo Stride Pro Elite",
        brand: "Summit",
        category: "men-shoes",
        price: 12999,
        tags: ["running"],
      },
    ],
    missing: [],
    resolved_at: "2026-08-08T00:00:00Z",
  })),
}));

import { RecommendationsCard } from "@/features/product/recommendations-card";

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RecommendationsCard id={PRODUCT_ID} />
    </QueryClientProvider>,
  );
}

describe("product detail recommendations", () => {
  it("resolves recommendation ids to real product names", async () => {
    // Regression: this container rendered every card as "Unnamed product",
    // because batch resolution was wired into the recommendation *explorer*
    // only. The card-level tests passed — they were handed metadata directly —
    // and nothing exercised the container that had to fetch it. That is why a
    // green suite still shipped placeholders to the screen.
    renderCard();

    expect(await screen.findByText("Demo Stride Pro Elite")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("Product has no name")).not.toBeInTheDocument();
      expect(screen.queryByText("Unnamed product")).not.toBeInTheDocument();
    });
  });
});
