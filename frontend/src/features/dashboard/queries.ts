"use client";

import { useQuery } from "@tanstack/react-query";

import { getDashboard, getPipelineReport } from "@/lib/api/endpoints/analytics";
import { getSystemHealth, getSystemStats } from "@/lib/api/endpoints/system";
import { queryKeys } from "@/lib/api";

/** Windowed usage metrics for the metric cards. */
export function useDashboard() {
  return useQuery({ queryKey: queryKeys.analytics.dashboard, queryFn: getDashboard });
}

/** Pipeline usage report over the trailing window. */
export function usePipelineReport() {
  return useQuery({ queryKey: queryKeys.analytics.pipeline, queryFn: getPipelineReport });
}

/** Live-ish system health; polled so the panel stays current. */
export function useSystemHealth() {
  return useQuery({
    queryKey: queryKeys.system.health,
    queryFn: getSystemHealth,
    refetchInterval: 30_000,
  });
}

/** Runtime statistics (queue depth, workers, dead-letter). */
export function useSystemStats() {
  return useQuery({
    queryKey: queryKeys.system.stats,
    queryFn: getSystemStats,
    refetchInterval: 30_000,
  });
}
