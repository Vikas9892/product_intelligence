"use client";

import { useMutation } from "@tanstack/react-query";

import {
  hasSearchInput,
  searchProductsTimed,
  type SearchParams,
} from "@/lib/api/endpoints/products";

/**
 * Runs a multi-modal search.
 *
 * A **mutation**, not a query, on purpose: the request body can contain a
 * `File`, which is not serializable into a stable React Query cache key, and a
 * search is an explicit user action rather than cache-backed view data. This
 * also keeps every submission a real backend call, so the reported latency
 * always describes a request that actually happened rather than a cache hit.
 */
export function useSearchProducts() {
  return useMutation({
    mutationFn: (params: SearchParams) => {
      if (!hasSearchInput(params)) {
        throw new Error("A text query or an image is required.");
      }
      return searchProductsTimed(params);
    },
  });
}
