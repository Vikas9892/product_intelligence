import type { AxiosProgressEvent } from "axios";

import { API_PREFIX, apiClient } from "../client";
import { apiGet, apiPost } from "../http";
import type {
  JobStatusResponse,
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
export function getJobStatus(productId: string): Promise<JobStatusResponse> {
  return apiGet<JobStatusResponse>(`${API_PREFIX}/products/${productId}/status`);
}

/** Recommendations for an already-processed product. */
export function getRecommendations(productId: string): Promise<RecommendationsResponse> {
  return apiGet<RecommendationsResponse>(`${API_PREFIX}/products/${productId}/recommendations`);
}

export interface SearchParams {
  query: string;
  topK?: number;
  brand?: string;
  category?: string;
  minPrice?: number;
  maxPrice?: number;
}

/**
 * Text search over indexed products (multipart). This is the only catalog
 * retrieval the backend offers — there is no "list all" endpoint — so the
 * product list is search-driven. Brand/category/price filters and `top_k` are
 * real backend parameters; results are ranked by relevance.
 */
export function searchProducts(params: SearchParams): Promise<ProductSearchResponse> {
  const body = new FormData();
  body.append("query", params.query);
  if (params.topK !== undefined) body.append("top_k", String(params.topK));
  if (params.brand) body.append("brand", params.brand);
  if (params.category) body.append("category", params.category);
  if (params.minPrice !== undefined) body.append("min_price", String(params.minPrice));
  if (params.maxPrice !== undefined) body.append("max_price", String(params.maxPrice));
  return apiPost<ProductSearchResponse>(`${API_PREFIX}/products/search`, body);
}
