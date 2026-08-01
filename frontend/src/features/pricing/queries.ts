"use client";

import { useMutation } from "@tanstack/react-query";

import { estimatePrice } from "@/lib/api/endpoints/pricing";
import type { PricingRequest } from "@/lib/api/types";

/**
 * Estimates a price for a described product. A mutation because it is an
 * explicit user action and every submission should be a real backend call, so
 * the reported latency always describes a request that actually happened.
 */
export function useEstimatePrice() {
  return useMutation({
    mutationFn: (body: PricingRequest) => estimatePrice(body),
  });
}
