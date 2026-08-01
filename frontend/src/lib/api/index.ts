/**
 * Public surface of the API layer. Import from `@/lib/api` rather than reaching
 * into individual modules.
 */
export { API_PREFIX, apiClient } from "./client";
export { apiDelete, apiGet, apiPost } from "./http";
export { apiGetTimed, apiPostTimed } from "./timing";
export type { LatencySource, TimedResponse } from "./timing";
export { ApiError, parseApiError } from "./errors";
export { getApiKey, setApiKey } from "./auth-token";
export { createQueryClient } from "./query-client";
export { queryKeys } from "./query-keys";
export type * from "./types";
