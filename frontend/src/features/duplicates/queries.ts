"use client";

import { useMutation } from "@tanstack/react-query";

import { checkDuplicate } from "@/lib/api/endpoints/duplicates";

// Candidate metadata is resolved through the shared
// `useResolveProductMetadata` hook in `@/features/products` — recommendations
// need the same id-to-fields lookup, so it lives in one place.
export { useResolveProducts as useCandidateMetadata } from "@/features/products/use-resolve-metadata";
export type { ProductMetaMap as CandidateMetaMap } from "@/features/products/use-resolve-metadata";

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
