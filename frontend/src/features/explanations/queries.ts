"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api";
import { getProductExplanations } from "@/lib/api/endpoints/explanations";

/**
 * A product's decision traces from `GET /products/{id}/explanations` — its
 * duplicate decision plus one trace per recommendation.
 *
 * Shared rather than owned by a single feature: product detail, the search
 * workspace, and the duplicate/recommendation views all read the same traces,
 * and one query key means they share one cache entry instead of refetching.
 *
 * `enabled` lets callers defer the request until the user actually asks for an
 * explanation, so opening a results page does not fan out one call per hit.
 */
export function useProductExplanations(id: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.products.explanations(id),
    queryFn: () => getProductExplanations(id),
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
  });
}
