import { API_PREFIX } from "../client";
import { apiGet } from "../http";
import { apiPostTimed, type TimedResponse } from "../timing";
import type { PricingRequest, PricingResponse } from "../types";

/**
 * Pricing endpoints (gated by `PRICING__ENABLED`). The by-id form estimates a
 * fair price for an already-indexed product from its comparables.
 */
export function getPricingById(productId: string): Promise<PricingResponse> {
  return apiGet<PricingResponse>(`${API_PREFIX}/pricing/${productId}`);
}

/**
 * Estimate a price for a *described* (not-yet-indexed) product. Retrieval uses
 * the product's text, so at least a `name` is required; `top_k` overrides the
 * configured `PRICING__TOP_K`.
 */
export function estimatePrice(body: PricingRequest): Promise<TimedResponse<PricingResponse>> {
  return apiPostTimed<PricingResponse>(`${API_PREFIX}/pricing/estimate`, body);
}
