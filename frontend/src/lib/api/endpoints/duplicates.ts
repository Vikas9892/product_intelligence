import { API_PREFIX } from "../client";
import { apiPostTimed, type TimedResponse } from "../timing";
import type { DuplicateCheckResponse } from "../types";

/**
 * Ad-hoc duplicate check (`POST /products/check-duplicate`).
 *
 * Takes the same multipart shape as upload (name + file, optional brand,
 * category, description, price) plus an optional `top_k`, and **never stores or
 * indexes anything** — it is a verification call, not an ingestion one.
 *
 * The body is built by the upload feature's `buildUploadFormData` so the two
 * callers cannot drift; `topK` is appended here because only this endpoint
 * accepts it.
 */
export function checkDuplicate(
  formData: FormData,
  options?: { topK?: number },
): Promise<TimedResponse<DuplicateCheckResponse>> {
  if (options?.topK !== undefined) {
    formData.set("top_k", String(options.topK));
  }
  return apiPostTimed<DuplicateCheckResponse>(`${API_PREFIX}/products/check-duplicate`, formData);
}
