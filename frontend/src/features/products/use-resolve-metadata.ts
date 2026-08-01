"use client";

import { useMutation } from "@tanstack/react-query";

import { searchProducts } from "@/lib/api/endpoints/products";
import { readProductMeta, type ProductMeta } from "@/lib/api/product-metadata";

/** Resolved descriptive fields, keyed by product id. */
export type ProductMetaMap = Record<string, ProductMeta>;

/**
 * Best-effort resolution of products' descriptive fields by id.
 *
 * Several responses identify products by id alone — duplicate candidates and
 * recommendations both do — and the backend has no get-product endpoint. The
 * only route to a product's stored fields is the search endpoint, whose results
 * carry the Qdrant metadata payload. So this runs a text search and keeps the
 * metadata of any returned product whose id was asked for.
 *
 * Strictly an enrichment. It never invents values: ids the search does not
 * surface simply have no entry, and callers are expected to say so rather than
 * render a blank that could read as real data.
 */
export function useResolveProductMetadata() {
  return useMutation({
    mutationFn: async ({
      text,
      productIds,
    }: {
      text: string;
      productIds: string[];
    }): Promise<ProductMetaMap> => {
      if (!text.trim() || productIds.length === 0) return {};

      const response = await searchProducts({
        query: text.trim(),
        topK: Math.max(20, productIds.length * 2),
      });

      const wanted = new Set(productIds);
      const resolved: ProductMetaMap = {};
      for (const result of response.results) {
        if (wanted.has(result.product_id)) {
          resolved[result.product_id] = readProductMeta(result.metadata);
        }
      }
      return resolved;
    },
  });
}
