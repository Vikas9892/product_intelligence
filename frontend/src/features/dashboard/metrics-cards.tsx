"use client";

import { CopyCheck, Gauge, Layers, Search, Sparkles, Upload } from "lucide-react";

import { StatCard } from "@/components/data/stat-card";
import { ErrorState } from "@/components/feedback/error-state";
import { StatGridSkeleton } from "@/components/feedback/loading-skeletons";
import { formatNumber } from "@/lib/format";

import { useDashboard } from "./queries";

function seconds(value: number): string {
  return `${formatNumber(value, { maximumFractionDigits: 2 })}s`;
}

/**
 * Top-of-dashboard metric row. Every value is a real count from the backend's
 * analytics daily buckets (today), with the trailing window shown as the hint.
 */
export function MetricsCards() {
  const { data, isPending, isError, refetch } = useDashboard();

  if (isPending) return <StatGridSkeleton count={6} />;
  if (isError) {
    return <ErrorState title="Couldn't load metrics" onRetry={() => void refetch()} />;
  }

  const { today, window, window_days } = data;
  const per = (n: number) => `${formatNumber(n)} in ${window_days}d`;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <StatCard
        label="Uploads today"
        value={formatNumber(today.uploads)}
        icon={Upload}
        hint={per(window.uploads)}
      />
      <StatCard
        label="Searches today"
        value={formatNumber(today.searches)}
        icon={Search}
        hint={per(window.searches)}
      />
      <StatCard
        label="Duplicate checks"
        value={formatNumber(today.duplicate_checks)}
        icon={CopyCheck}
        hint={per(window.duplicate_checks)}
      />
      <StatCard
        label="Recommendations"
        value={formatNumber(today.recommendations)}
        icon={Sparkles}
        hint={per(window.recommendations)}
      />
      <StatCard
        label="Avg processing"
        value={seconds(today.average_processing_seconds)}
        icon={Gauge}
        hint={`${seconds(window.average_processing_seconds)} avg (${window_days}d)`}
      />
      <StatCard label="Active models" value={formatNumber(data.active_models)} icon={Layers} />
    </div>
  );
}
