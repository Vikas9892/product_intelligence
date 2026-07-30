import { API_PREFIX } from "../client";
import { apiGet } from "../http";
import type { PricingResponse } from "../types";

/**
 * Pricing endpoints (gated by `PRICING__ENABLED`). The by-id form estimates a
 * fair price for an already-indexed product from its comparables.
 */
export function getPricingById(productId: string): Promise<PricingResponse> {
  return apiGet<PricingResponse>(`${API_PREFIX}/pricing/${productId}`);
}
