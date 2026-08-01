"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api";
import { getRecommendations } from "@/lib/api/endpoints/products";

/**
 * A product's recommendations (`GET /products/{id}/recommendations`).
 *
 * Shared by product detail and the recommendation explorer so both hit one
 * cache entry. `enabled` defers the call until a product is actually selected.
 */
export function useProductRecommendations(id: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.products.recommendations(id ?? ""),
    queryFn: () => getRecommendations(id as string),
    enabled: Boolean(id) && (options?.enabled ?? true),
    staleTime: 60_000,
  });
}
