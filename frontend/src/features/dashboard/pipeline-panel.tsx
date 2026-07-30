"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { formatDate, formatNumber } from "@/lib/format";

import { usePipelineReport } from "./queries";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}

/**
 * Pipeline activity over the reporting window, from `/analytics/pipeline`.
 * Aggregate counts only — the backend exposes no per-item activity feed, so
 * this shows the honest window totals rather than a fabricated recent list.
 */
export function PipelinePanel() {
  const { data, isPending, isError, refetch } = usePipelineReport();

  if (isPending) return <CardSkeleton />;
  if (isError) {
    return <ErrorState title="Couldn't load pipeline activity" onRetry={() => void refetch()} />;
  }

  const { usage } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pipeline activity</CardTitle>
        <CardDescription>
          {formatDate(data.start_date)} – {formatDate(data.end_date)} ({data.period})
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Row label="Uploads" value={formatNumber(usage.uploads)} />
        <Row label="Searches" value={formatNumber(usage.searches)} />
        <Row label="Duplicate checks" value={formatNumber(usage.duplicate_checks)} />
        <Row label="Recommendations" value={formatNumber(usage.recommendations)} />
        <Row
          label="Avg processing"
          value={`${formatNumber(usage.average_processing_seconds, { maximumFractionDigits: 2 })}s`}
        />
      </CardContent>
    </Card>
  );
}
