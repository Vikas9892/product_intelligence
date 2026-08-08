import type { AxiosProgressEvent } from "axios";

import { API_PREFIX, apiClient } from "../client";
import { apiGet, apiPost } from "../http";
import { apiPostTimed, type TimedResponse } from "../timing";
import type {
  JobStatusResponse,
  ProductBatchResponse,
  ProductSummary,
  ProductSearchResponse,
  RecommendationsResponse,
  UploadAcceptedResponse,
  UploadResponse,
} from "../types";

/** Discriminates the async (202) upload response from the sync (201) one. */
export type UploadResult = UploadResponse | UploadAcceptedResponse;

export function isAccepted(result: UploadResult): result is UploadAcceptedResponse {
  return "job_id" in result;
}

/**
 * Upload a product image + metadata (multipart). Returns `202` with a job to
 * poll (async pipeline, the default) or `201` with the finished product (sync
 * mode). `onUploadProgress` drives the upload progress bar; the browser sets
 * the multipart boundary automatically for a `FormData` body.
 */
export function uploadProduct(
  formData: FormData,
  options?: { onUploadProgress?: (event: AxiosProgressEvent) => void; signal?: AbortSignal },
): Promise<UploadResult> {
  return apiClient
    .post<UploadResult>(`${API_PREFIX}/products/upload`, formData, {
      onUploadProgress: options?.onUploadProgress,
      signal: options?.signal,
    })
    .then((response) => response.data);
}

/** Poll a product's background processing job. */
/** Resolve one product id to its stored catalog metadata. Throws 404 if unknown. */
export function getProduct(productId: string): Promise<ProductSummary> {
  return apiGet<ProductSummary>(`${API_PREFIX}/products/${productId}`);
}

/**
 * Resolve many product ids in one round trip.
 *
 * Recommendations, duplicate candidates and explanations all return bare ids.
 * Resolving them one request per card would be N round trips for a single
 * view; this is one. Unknown ids come back in `missing` rather than failing the
 * request, so a partially-stale list still renders what exists.
 */
export function getProductsBatch(productIds: string[]): Promise<ProductBatchResponse> {
  return apiPost<ProductBatchResponse>(`${API_PREFIX}/products/batch`, {
    product_ids: productIds,
  });
}

export function getJobStatus(productId: string): Promise<JobStatusResponse> {
  return apiGet<JobStatusResponse>(`${API_PREFIX}/products/${productId}/status`);
}

/** Recommendations for an already-processed product. */
export function getRecommendations(productId: string): Promise<RecommendationsResponse> {
  return apiGet<RecommendationsResponse>(`${API_PREFIX}/products/${productId}/recommendations`);
}

/**
 * Parameters for `POST /products/search`.
 *
 * `query` and `file` are both optional individually but the backend requires
 * **at least one** — that is what makes the endpoint multi-modal:
 *
 * - `query` alone  -> text search (BGE text embedding)
 * - `file` alone   -> image search (CLIP image embedding)
 * - both           -> hybrid, fused server-side by the configured weights
 *
 * Use {@link hasSearchInput} to check before dispatching.
 */
export interface SearchParams {
  query?: string;
  file?: File;
  topK?: number;
  brand?: string;
  category?: string;
  minPrice?: number;
  maxPrice?: number;
}

/** Whether `params` satisfies the backend's "query or image required" rule. */
export function hasSearchInput(params: SearchParams | null | undefined): boolean {
  if (!params) return false;
  return Boolean(params.query?.trim()) || params.file instanceof File;
}

/**
 * Builds the multipart body once, so the plain and timed search calls cannot
 * drift apart. Empty/undefined values are omitted rather than sent blank —
 * the backend treats a present-but-empty filter differently from an absent one.
 */
function buildSearchFormData(params: SearchParams): FormData {
  const body = new FormData();
  const query = params.query?.trim();
  if (query) body.append("query", query);
  if (params.file) body.append("file", params.file);
  if (params.topK !== undefined) body.append("top_k", String(params.topK));
  if (params.brand) body.append("brand", params.brand);
  if (params.category) body.append("category", params.category);
  if (params.minPrice !== undefined) body.append("min_price", String(params.minPrice));
  if (params.maxPrice !== undefined) body.append("max_price", String(params.maxPrice));
  return body;
}

/**
 * Multi-modal search over indexed products (multipart). This is the only
 * catalog retrieval the backend offers — there is no "list all" endpoint — so
 * browsing is search-driven. Brand/category/price filters and `top_k` are real
 * backend parameters; results come back ranked by fused relevance.
 */
export function searchProducts(params: SearchParams): Promise<ProductSearchResponse> {
  return apiPost<ProductSearchResponse>(
    `${API_PREFIX}/products/search`,
    buildSearchFormData(params),
  );
}

/**
 * {@link searchProducts} that additionally reports the backend's own measured
 * handling time, for the search workspace's latency readout.
 */
export function searchProductsTimed(
  params: SearchParams,
): Promise<TimedResponse<ProductSearchResponse>> {
  return apiPostTimed<ProductSearchResponse>(
    `${API_PREFIX}/products/search`,
    buildSearchFormData(params),
  );
}
