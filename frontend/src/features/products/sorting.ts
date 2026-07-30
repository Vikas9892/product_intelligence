import { readProductMeta } from "@/lib/api/product-metadata";
import type { ProductSearchResult } from "@/lib/api/types";

export type SortKey = "relevance" | "price" | "name";
export type SortDir = "asc" | "desc";

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "price", label: "Price" },
  { value: "name", label: "Name" },
];

/**
 * Client-side sort of the fetched result set. The backend returns results by
 * relevance and offers no sort parameter, so re-ordering the retrieved page
 * happens here. Missing values sort last.
 */
export function sortResults(
  results: ProductSearchResult[],
  key: SortKey,
  dir: SortDir,
): ProductSearchResult[] {
  const factor = dir === "asc" ? 1 : -1;
  const copy = [...results];

  copy.sort((a, b) => {
    if (key === "relevance") return (a.score - b.score) * factor;
    if (key === "price") {
      const pa = readProductMeta(a.metadata).price ?? Infinity;
      const pb = readProductMeta(b.metadata).price ?? Infinity;
      return (pa - pb) * factor;
    }
    const na = readProductMeta(a.metadata).name ?? "";
    const nb = readProductMeta(b.metadata).name ?? "";
    return na.localeCompare(nb) * factor;
  });

  return copy;
}
