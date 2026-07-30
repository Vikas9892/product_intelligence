"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { getJobStatus, uploadProduct, type UploadResult } from "@/lib/api/endpoints/products";
import { queryKeys } from "@/lib/api";
import type { JobStatusResponse } from "@/lib/api/types";

/** Terminal job states — polling stops once one is reached. */
export const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export function isTerminal(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}

/**
 * Upload mutation. `onProgress` receives 0..100 during the request body upload;
 * `getSignal` supplies an AbortSignal so the in-flight upload can be cancelled
 * (server-side processing cannot be cancelled — the backend has no such state).
 */
export function useUploadProduct(
  onProgress?: (percent: number) => void,
  getSignal?: () => AbortSignal | undefined,
) {
  return useMutation<UploadResult, Error, FormData>({
    mutationFn: (formData) =>
      uploadProduct(formData, {
        signal: getSignal?.(),
        onUploadProgress: (event) => {
          if (event.total) {
            onProgress?.(Math.round((event.loaded / event.total) * 100));
          }
        },
      }),
  });
}

/**
 * Polls a product's processing job until it reaches a terminal state, then
 * stops. Disabled until a `productId` exists.
 */
export function useJobStatus(productId: string | null) {
  return useQuery<JobStatusResponse>({
    queryKey: queryKeys.products.status(productId ?? ""),
    queryFn: () => getJobStatus(productId as string),
    enabled: Boolean(productId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isTerminal(status) ? false : 1500;
    },
  });
}
