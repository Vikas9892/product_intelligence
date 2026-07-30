import { API_PREFIX } from "../client";
import { apiGet } from "../http";
import type { SystemHealthResponse, SystemStatsResponse } from "../types";

/**
 * Operational endpoints (gated by `METRICS__HEALTH_ENDPOINTS_ENABLED`). These
 * are the versioned system dashboards, distinct from the unversioned
 * `/health` liveness probe.
 */

export function getSystemHealth(): Promise<SystemHealthResponse> {
  return apiGet<SystemHealthResponse>(`${API_PREFIX}/system/health`);
}

export function getSystemStats(): Promise<SystemStatsResponse> {
  return apiGet<SystemStatsResponse>(`${API_PREFIX}/system/stats`);
}
