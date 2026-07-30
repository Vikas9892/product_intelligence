import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./errors";

/**
 * Number of retry attempts for a failed, retryable query.
 */
const MAX_QUERY_RETRIES = 2;

/**
 * Builds the app's `QueryClient` with the shared retry and caching policy.
 *
 * **Retry policy:** client errors (4xx) are never retried — they will not
 * succeed on a repeat. Network faults and server errors (5xx) are retried up to
 * {@link MAX_QUERY_RETRIES} times with exponential backoff. Mutations are never
 * retried automatically, since they are typically not idempotent.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < MAX_QUERY_RETRIES;
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 15_000),
      },
      mutations: {
        retry: false,
      },
    },
  });
}
