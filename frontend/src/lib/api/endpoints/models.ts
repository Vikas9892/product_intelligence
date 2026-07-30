import { API_PREFIX } from "../client";
import { apiGet } from "../http";
import type { ModelInfoResponse } from "../types";

/** Model registry: the active model per type (image, text, reranker). */
export function getModels(): Promise<ModelInfoResponse[]> {
  return apiGet<ModelInfoResponse[]>(`${API_PREFIX}/models`);
}
