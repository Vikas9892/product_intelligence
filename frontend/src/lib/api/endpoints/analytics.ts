import { API_PREFIX } from "../client";
import { apiGet } from "../http";
import type { AnalyticsReportResponse, DashboardResponse, ModelAnalyticsResponse } from "../types";

/**
 * Analytics endpoints (gated by `ANALYTICS__ENABLED` on the backend). All are
 * read-only aggregates over Redis daily buckets.
 */

export function getDashboard(): Promise<DashboardResponse> {
  return apiGet<DashboardResponse>(`${API_PREFIX}/analytics/dashboard`);
}

export function getPipelineReport(): Promise<AnalyticsReportResponse> {
  return apiGet<AnalyticsReportResponse>(`${API_PREFIX}/analytics/pipeline`);
}

export function getModelAnalytics(): Promise<ModelAnalyticsResponse> {
  return apiGet<ModelAnalyticsResponse>(`${API_PREFIX}/analytics/models`);
}
