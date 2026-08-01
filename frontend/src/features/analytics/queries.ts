"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api";
import {
  getDashboard,
  getModelAnalytics,
  getPipelineReport,
  getTrends,
  TREND_METRICS,
  type TrendGranularity,
  type TrendMetric,
} from "@/lib/api/endpoints/analytics";
import { getSystemStats } from "@/lib/api/endpoints/system";

const STALE = 30_000;

export function useDashboardAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.dashboard,
    queryFn: getDashboard,
    staleTime: STALE,
  });
}

export function usePipelineAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.pipeline,
    queryFn: getPipelineReport,
    staleTime: STALE,
  });
}

export function useModelAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.models,
    queryFn: getModelAnalytics,
    staleTime: STALE,
  });
}

export function useRuntimeStats() {
  return useQuery({
    queryKey: queryKeys.system.stats,
    queryFn: getSystemStats,
    refetchInterval: STALE,
  });
}

/**
 * All four event trends over the same window.
 *
 * `/analytics/trends` reports one metric per call, so four parallel queries are
 * issued rather than one — the fan-out is the endpoint's shape, not a choice.
 * Each keeps its own cache entry, so switching granularity refetches only what
 * actually changed.
 */
export function useAllTrends(granularity: TrendGranularity, periods: number) {
  return useQueries({
    queries: TREND_METRICS.map((metric: TrendMetric) => ({
      queryKey: queryKeys.analytics.trends({ metric, granularity, periods }),
      queryFn: () => getTrends({ metric, granularity, periods }),
      staleTime: STALE,
    })),
  });
}
