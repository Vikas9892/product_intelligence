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

/** The countable events the backend tallies (`AnalyticsEvent`). */
export const TREND_METRICS = ["upload", "search", "duplicate_check", "recommendation"] as const;
export type TrendMetric = (typeof TREND_METRICS)[number];

/** Fixed-length trend buckets: daily = 1 day, weekly = 7, monthly = 30. */
export const TREND_GRANULARITIES = ["daily", "weekly", "monthly"] as const;
export type TrendGranularity = (typeof TREND_GRANULARITIES)[number];

/**
 * One trend point. Typed by hand because `/analytics/trends` declares
 * `response_model=None` on the backend (it also serves Markdown), so
 * `openapi-typescript` generates no schema for it. Mirrors `TrendPointInfo`.
 */
export interface TrendPoint {
  period_start: string;
  value: number;
}

/** Mirrors the backend's `TrendReportResponse`. */
export interface TrendReport {
  metric: string;
  granularity: string;
  points: TrendPoint[];
  generated_at: string;
}

/**
 * Trend for one metric. `periods` is capped at 90 by the backend.
 *
 * The `format` parameter (JSON vs Markdown) is deliberately not exposed — the
 * UI only ever consumes JSON.
 */
export function getTrends(params: {
  metric: TrendMetric;
  granularity?: TrendGranularity;
  periods?: number;
}): Promise<TrendReport> {
  const search = new URLSearchParams({ metric: params.metric });
  if (params.granularity) search.set("granularity", params.granularity);
  if (params.periods !== undefined) search.set("periods", String(params.periods));
  return apiGet<TrendReport>(`${API_PREFIX}/analytics/trends?${search.toString()}`);
}
