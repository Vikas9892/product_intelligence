"use client";

import { useMutation } from "@tanstack/react-query";

import { checkDuplicate } from "@/lib/api/endpoints/duplicates";
import { searchProducts } from "@/lib/api/endpoints/products";
import { readProductMeta, type ProductMeta } from "@/lib/api/product-metadata";

/**
 * Runs a duplicate check. A mutation because it carries a `File` and is an
 * explicit user action, and because every submission should be a real call
 * rather than a cache hit.
 */
export function useCheckDuplicate() {
  return useMutation({
    mutationFn: ({ formData, topK }: { formData: FormData; topK?: number }) =>
      checkDuplicate(formData, { topK }),
  });
}

/** Resolved descriptive fields for candidate products, keyed by product id. */
export type CandidateMetaMap = Record<string, ProductMeta>;

/**
 * Best-effort lookup of the candidates' descriptive fields.
 *
 * The duplicate response identifies candidates by id only, and the backend has
 * no get-product endpoint. The one way to obtain a product's stored fields is
 * the search endpoint, whose results carry the Qdrant metadata payload — so
 * this runs a text search built from the same product text and keeps the
 * metadata of any returned product whose id matches a candidate.
 *
 * Strictly an enrichment: it never invents values, and any candidate the search
 * does not surface simply has no metadata, which the comparison view states
 * rather than papers over.
 */
export function useCandidateMetadata() {
  return useMutation({
    mutationFn: async ({
      text,
      candidateIds,
    }: {
      text: string;
      candidateIds: string[];
    }): Promise<CandidateMetaMap> => {
      if (!text.trim() || candidateIds.length === 0) return {};

      const response = await searchProducts({
        query: text.trim(),
        topK: Math.max(20, candidateIds.length * 2),
      });

      const wanted = new Set(candidateIds);
      const resolved: CandidateMetaMap = {};
      for (const result of response.results) {
        if (wanted.has(result.product_id)) {
          resolved[result.product_id] = readProductMeta(result.metadata);
        }
      }
      return resolved;
    },
  });
}
