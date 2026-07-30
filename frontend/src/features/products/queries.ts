"use client";

import { useQuery } from "@tanstack/react-query";

import { searchProducts, type SearchParams } from "@/lib/api/endpoints/products";
import { queryKeys } from "@/lib/api";

/**
 * Product search query. Disabled until a non-empty query is submitted (the
 * backend requires a query or image). Results are cached per parameter set.
 */
export function useProductSearch(params: SearchParams | null) {
  return useQuery({
    queryKey: queryKeys.search({ ...(params ?? { query: "" }) }),
    queryFn: () => searchProducts(params as SearchParams),
    enabled: Boolean(params && params.query.trim()),
    staleTime: 60_000,
  });
}
