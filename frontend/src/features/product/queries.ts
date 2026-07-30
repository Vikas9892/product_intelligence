"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getProductExplanations } from "@/lib/api/endpoints/explanations";
import { getModels } from "@/lib/api/endpoints/models";
import { getPricingById } from "@/lib/api/endpoints/pricing";
import { getRecommendations } from "@/lib/api/endpoints/products";
import { queryKeys } from "@/lib/api";
import type { ProductSearchResult } from "@/lib/api/types";

/**
 * Reads product metadata seeded by the search result that navigated here. The
 * backend has no get-product endpoint, so this cache is the only source of a
 * product's own descriptive fields; it is absent on direct navigation.
 */
export function useProductMetaCache(id: string): ProductSearchResult | undefined {
  const queryClient = useQueryClient();
  return queryClient.getQueryData<ProductSearchResult>(queryKeys.products.meta(id));
}

export function useRecommendations(id: string) {
  return useQuery({
    queryKey: queryKeys.products.recommendations(id),
    queryFn: () => getRecommendations(id),
  });
}

export function usePricing(id: string) {
  return useQuery({ queryKey: queryKeys.pricing.byId(id), queryFn: () => getPricingById(id) });
}

export function useExplanations(id: string) {
  return useQuery({
    queryKey: queryKeys.products.explanations(id),
    queryFn: () => getProductExplanations(id),
  });
}

export function useModels() {
  return useQuery({ queryKey: queryKeys.models.list, queryFn: getModels, staleTime: 5 * 60_000 });
}
