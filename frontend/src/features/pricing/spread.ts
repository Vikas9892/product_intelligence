import type { ComparableProductInfo } from "@/lib/api/types";

/**
 * Plain descriptive statistics over the comparables the backend returned.
 *
 * These are **not** backend figures and must never be presented as such — they
 * summarize the list in the response so a reader can see its spread. The
 * backend's own outputs are `estimated_price`, `confidence`, `confidence_score`,
 * and `strategy`; nothing here re-derives or second-guesses those.
 */
export interface PriceSpread {
  count: number;
  min: number;
  median: number;
  max: number;
  /** Where `estimated_price` sits within [min, max], as 0..1. Null if flat. */
  estimatePosition: number | null;
}

function median(sorted: number[]): number {
  if (sorted.length === 0) return 0;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

export function computeSpread(
  comparables: ComparableProductInfo[],
  // `null` when no estimate was made — absence is not zero.
  estimatedPrice: number | null,
): PriceSpread | null {
  if (comparables.length === 0 || estimatedPrice === null) return null;

  const prices = comparables.map((c) => c.price).sort((a, b) => a - b);
  const min = prices[0];
  const max = prices[prices.length - 1];
  const range = max - min;

  return {
    count: prices.length,
    min,
    median: median(prices),
    max,
    estimatePosition: range > 0 ? Math.min(1, Math.max(0, (estimatedPrice - min) / range)) : null,
  };
}

/** Bars for the distribution chart, sorted cheapest-first for a readable ramp. */
export function toDistributionData(
  comparables: ComparableProductInfo[],
): { id: string; label: string; price: number; similarity: number }[] {
  return [...comparables]
    .sort((a, b) => a.price - b.price)
    .map((c) => ({
      id: c.product_id,
      label: c.name ?? `${c.product_id.slice(0, 8)}…`,
      price: c.price,
      similarity: c.similarity,
    }));
}

/**
 * Human copy for the confidence level the backend reported.
 *
 * The level itself is the backend's (`confidence`), as is `confidence_score`;
 * this only explains what drives it, per the documented pricing settings.
 */
export const CONFIDENCE_EXPLANATION: Record<string, string> = {
  low: "Few comparables, or widely spread prices. Below PRICING__MIN_COMPARABLES the backend caps confidence at low regardless of agreement.",
  medium: "A workable number of comparables with moderate price agreement.",
  high: "Many closely-priced comparables with strong similarity to the described product.",
};

/** What each aggregation strategy does, for the explainability panel. */
export const STRATEGY_EXPLANATION: Record<string, string> = {
  trimmed_mean:
    "Drops the cheapest and most expensive PRICING__TRIM_RATIO of the surviving comparables, then averages the rest — resistant to a single extreme price.",
  weighted_average:
    "Averages the comparables weighted by their similarity, so closer matches pull the estimate harder.",
  median: "Takes the middle price of the surviving comparables — maximally resistant to outliers.",
};
