import { API_PREFIX } from "../client";
import { apiGet } from "../http";
import type { ProductExplanationsResponse } from "../types";

/**
 * Explainability endpoints. The aggregate product view bundles the duplicate
 * decision trace and per-recommendation traces for a product.
 */
export function getProductExplanations(productId: string): Promise<ProductExplanationsResponse> {
  return apiGet<ProductExplanationsResponse>(`${API_PREFIX}/products/${productId}/explanations`);
}
