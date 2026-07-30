import type { AxiosProgressEvent } from "axios";

import { API_PREFIX, apiClient } from "../client";
import { apiGet } from "../http";
import type {
  JobStatusResponse,
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
