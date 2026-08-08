"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getModels } from "@/lib/api/endpoints/models";
import { getProduct } from "@/lib/api/endpoints/products";
import { getPricingById } from "@/lib/api/endpoints/pricing";
import { queryKeys } from "@/lib/api";
import type { ProductSearchResult } from "@/lib/api/types";

/**
 * Reads product metadata seeded by the search result that navigated here.
 *
 * Kept as an *instant-render* optimisation only: when you arrive from search,
 * the fields are already in cache, so the page paints without waiting. It is
 * no longer the only source — `useProduct` fetches authoritatively — and it is
 * absent on direct navigation, which is exactly why the fetch exists.
 */
export function useProductMetaCache(id: string): ProductSearchResult | undefined {
  const queryClient = useQueryClient();
  return queryClient.getQueryData<ProductSearchResult>(queryKeys.products.meta(id));
}

// Recommendations are read through `@/features/recommendations/queries`
// (`useProductRecommendations`) — shared with the recommendation explorer so
// both hit the same cache entry.

/**
 * The product itself, from `GET /products/{id}`.
 *
 * The authoritative source for a product's own fields. Before this endpoint
 * existed the detail page could only show what a search result had carried in,
 * so direct navigation showed nothing and the UI explained the gap. That gap
 * is closed; the explanation is gone.
 */
export function useProduct(id: string) {
  return useQuery({
    queryKey: queryKeys.products.detail(id),
    queryFn: () => getProduct(id),
    staleTime: 60_000,
    // A product that is not indexed is a real, terminal answer, not a blip.
    retry: false,
  });
}

export function usePricing(id: string) {
  return useQuery({ queryKey: queryKeys.pricing.byId(id), queryFn: () => getPricingById(id) });
}

// Explanations are read through `@/features/explanations/queries`
// (`useProductExplanations`) — shared, because search and the intelligence
// views read the same traces and should hit the same cache entry.

export function useModels() {
  return useQuery({ queryKey: queryKeys.models.list, queryFn: getModels, staleTime: 5 * 60_000 });
}
