import type { RecommendationInfo } from "@/lib/api/types";

export type RecommendationSortKey = "score" | "attributes" | "tags";
export type SortDir = "asc" | "desc";

export const RECOMMENDATION_SORT_OPTIONS: { value: RecommendationSortKey; label: string }[] = [
  { value: "score", label: "Score" },
  { value: "attributes", label: "Matched attributes" },
  { value: "tags", label: "Matched tags" },
];

/**
 * The overlap filters a caller can apply. Each maps to a field the backend
 * actually returns on `RecommendationReasonInfo`, so a filter never asks a
 * question the data cannot answer.
 */
export interface RecommendationFilters {
  /** Keep only recommendations sharing the target's brand. */
  sharedBrand: boolean;
  /** Keep only recommendations sharing the target's category. */
  sharedCategory: boolean;
  /** Keep only recommendations with at least one matched attribute. */
  hasAttributes: boolean;
  /** Minimum score, 0..1. */
  minScore: number;
}

export const DEFAULT_RECOMMENDATION_FILTERS: RecommendationFilters = {
  sharedBrand: false,
  sharedCategory: false,
  hasAttributes: false,
  minScore: 0,
};

function attributeCount(rec: RecommendationInfo): number {
  return rec.reason.matched_attributes?.length ?? 0;
}

function tagCount(rec: RecommendationInfo): number {
  return rec.reason.matched_tags?.length ?? 0;
}

/**
 * Applies the overlap filters.
 *
 * Filtering happens client-side because the recommendations endpoint takes no
 * filter parameters — it returns one ranked set, and narrowing it here does not
 * change what the backend decided, only which of its results are displayed.
 */
export function filterRecommendations(
  recommendations: RecommendationInfo[],
  filters: RecommendationFilters,
): RecommendationInfo[] {
  return recommendations.filter((rec) => {
    if (filters.sharedBrand && !rec.reason.shared_brand) return false;
    if (filters.sharedCategory && !rec.reason.shared_category) return false;
    if (filters.hasAttributes && attributeCount(rec) === 0) return false;
    if (rec.score < filters.minScore) return false;
    return true;
  });
}

/**
 * Re-orders the fetched set. The backend returns them ranked by its own final
 * score; sorting by matched attributes or tags is an alternative view of the
 * same data, never a re-scoring.
 */
export function sortRecommendations(
  recommendations: RecommendationInfo[],
  key: RecommendationSortKey,
  dir: SortDir,
): RecommendationInfo[] {
  const factor = dir === "asc" ? 1 : -1;
  const copy = [...recommendations];

  copy.sort((a, b) => {
    if (key === "attributes") return (attributeCount(a) - attributeCount(b)) * factor;
    if (key === "tags") return (tagCount(a) - tagCount(b)) * factor;
    return (a.score - b.score) * factor;
  });

  return copy;
}

/** Counts used for the filter summary line. */
export function overlapSummary(recommendations: RecommendationInfo[]): {
  sharedBrand: number;
  sharedCategory: number;
  withAttributes: number;
} {
  return {
    sharedBrand: recommendations.filter((r) => r.reason.shared_brand).length,
    sharedCategory: recommendations.filter((r) => r.reason.shared_category).length,
    withAttributes: recommendations.filter((r) => attributeCount(r) > 0).length,
  };
}
