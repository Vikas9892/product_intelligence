"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api";
import { getProductsBatch } from "@/lib/api/endpoints/products";
import type { ProductMeta } from "@/lib/api/product-metadata";

/** Resolved descriptive fields, keyed by product id. */
export type ProductMetaMap = Record<string, ProductMeta>;

/** Ids that were asked for but are not indexed. Distinct from "not yet loaded". */
export type ProductResolution = {
  meta: ProductMetaMap;
  missing: Set<string>;
};

/**
 * Resolve products by id, in one request.
 *
 * Several responses identify products by id alone — recommendations and
 * duplicate candidates both do. This resolves those ids through
 * `POST /products/batch`.
 *
 * It previously could not. With no get-product endpoint, the only route to a
 * product's stored fields was the *search* endpoint, so this ran a text search
 * and kept whichever requested ids happened to appear in the results. Ids the
 * search did not surface had no entry, and the UI rendered them as "Unresolved
 * product" — which was every card, because a recommendation set is precisely
 * the products a text query does not necessarily return.
 *
 * Now a `useQuery` rather than a `useMutation`: resolution is a read, so it
 * caches. Two views asking for the same products share one cache entry, and a
 * re-render does not refetch.
 *
 * `missing` carries ids the backend confirmed are not indexed, so a caller can
 * render a real "product not found" state — distinguishable from "still
 * loading" and from "resolved but unnamed".
 */
export function useResolveProducts(productIds: string[], options?: { enabled?: boolean }) {
  // Sorted and de-duplicated so the cache key depends on the *set* of ids, not
  // the order a particular view happened to render them in.
  const ids = Array.from(new Set(productIds)).sort();

  return useQuery({
    queryKey: queryKeys.products.batch(ids),
    enabled: (options?.enabled ?? true) && ids.length > 0,
    queryFn: async (): Promise<ProductResolution> => {
      const response = await getProductsBatch(ids);

      const meta: ProductMetaMap = {};
      for (const product of response.products ?? []) {
        // `?? undefined` rather than `?? null`: ProductMeta's fields are
        // optional, and an absent value must read as absent everywhere.
        meta[product.product_id] = {
          name: product.name ?? undefined,
          brand: product.brand ?? undefined,
          category: product.category ?? undefined,
          price: product.price ?? undefined,
          description: product.description ?? undefined,
          color: product.color ?? undefined,
          material: product.material ?? undefined,
          gender: product.gender ?? undefined,
          season: product.season ?? undefined,
          style: product.style ?? undefined,
          tags: product.tags ?? [],
          qualityScore: product.quality_score ?? undefined,
        };
      }
      return { meta, missing: new Set(response.missing ?? []) };
    },
    // Product metadata changes only when a product is re-ingested, so a short
    // stale window avoids refetching while a user moves between views.
    staleTime: 60_000,
  });
}
