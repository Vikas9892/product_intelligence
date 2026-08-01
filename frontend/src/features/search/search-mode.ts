import type { SearchParams } from "@/lib/api/endpoints/products";

/**
 * The three retrieval modes `POST /products/search` supports, named after what
 * the backend actually does with the input rather than after the UI control.
 */
export type SearchMode = "text" | "image" | "hybrid";

export const SEARCH_MODES: {
  value: SearchMode;
  label: string;
  /** What the backend does in this mode — shown as help text, not decoration. */
  hint: string;
}[] = [
  { value: "text", label: "Text", hint: "Semantic text match over product text embeddings." },
  { value: "image", label: "Image", hint: "Visual similarity over product image embeddings." },
  {
    value: "hybrid",
    label: "Hybrid",
    hint: "Both signals, fused server-side into a single relevance score.",
  },
];

/** What a given mode needs before it can be submitted. */
export function modeRequirements(mode: SearchMode): { needsQuery: boolean; needsImage: boolean } {
  return {
    needsQuery: mode === "text" || mode === "hybrid",
    needsImage: mode === "image" || mode === "hybrid",
  };
}

/**
 * Whether the draft satisfies its mode. Enforced client-side purely so the UI
 * can disable the button with a reason — the backend remains the real
 * validator and its `422` is still surfaced if anything slips through.
 */
export function isModeSatisfied(
  mode: SearchMode,
  draft: { query: string; file: File | null },
): boolean {
  const { needsQuery, needsImage } = modeRequirements(mode);
  if (needsQuery && !draft.query.trim()) return false;
  if (needsImage && !draft.file) return false;
  return true;
}

/** Human-readable reason the submit button is disabled, or `null` when ready. */
export function unmetRequirement(
  mode: SearchMode,
  draft: { query: string; file: File | null },
): string | null {
  const { needsQuery, needsImage } = modeRequirements(mode);
  const missingQuery = needsQuery && !draft.query.trim();
  const missingImage = needsImage && !draft.file;

  if (missingQuery && missingImage) return "Enter a query and choose an image.";
  if (missingQuery) return "Enter a search query.";
  if (missingImage) return "Choose an image to search with.";
  return null;
}

/**
 * Builds the request for a mode, sending only the inputs that mode uses. A
 * stale image is not sent in text mode (and vice versa), so the mode the user
 * picked is exactly the retrieval the backend performs.
 */
export function buildSearchParams(
  mode: SearchMode,
  draft: {
    query: string;
    file: File | null;
    topK: number;
    brand: string;
    category: string;
    minPrice: string;
    maxPrice: string;
  },
): SearchParams {
  const { needsQuery, needsImage } = modeRequirements(mode);
  return {
    query: needsQuery ? draft.query.trim() : undefined,
    file: needsImage && draft.file ? draft.file : undefined,
    topK: draft.topK,
    brand: draft.brand.trim() || undefined,
    category: draft.category.trim() || undefined,
    minPrice: draft.minPrice.trim() !== "" ? Number(draft.minPrice) : undefined,
    maxPrice: draft.maxPrice.trim() !== "" ? Number(draft.maxPrice) : undefined,
  };
}

/** Which modalities the backend reports a result matched on. */
export function describeModalities(matched: string[]): string {
  if (matched.length === 0) return "No modality reported";
  if (matched.length > 1) return `Matched on ${matched.join(" + ")}`;
  return `Matched on ${matched[0]}`;
}
