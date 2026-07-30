"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusChip, type StatusTone } from "@/components/data/status-chip";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { formatNumber } from "@/lib/format";

import { useSystemHealth, useSystemStats } from "./queries";

/** Map a backend health string ("ok"/anything else) to a status tone. */
function tone(value: string): StatusTone {
  return value.toLowerCase() === "ok" ? "success" : "danger";
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{children}</span>
    </div>
  );
}

/**
 * Operational panel: dependency health and runtime statistics, from
 * `/system/health` and `/system/stats`. Polled on an interval by the queries.
 */
export function SystemPanel() {
  const health = useSystemHealth();
  const stats = useSystemStats();

  if (health.isPending || stats.isPending) return <CardSkeleton />;
  if (health.isError || stats.isError) {
    return (
      <ErrorState
        title="Couldn't load system status"
        onRetry={() => {
          void health.refetch();
          void stats.refetch();
        }}
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>System</CardTitle>
        <CardDescription>Live dependency health and worker runtime.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-2">
        <div>
          <Row label="Redis">
            <StatusChip tone={tone(health.data.redis)} label={health.data.redis} />
          </Row>
          <Row label="Qdrant">
            <StatusChip tone={tone(health.data.qdrant)} label={health.data.qdrant} />
          </Row>
          <Row label="Workers">{formatNumber(health.data.workers)}</Row>
          <Row label="Uptime">{health.data.uptime}</Row>
        </div>
        <div>
          <Row label="Queue depth">{formatNumber(stats.data.queue_depth)}</Row>
          <Row label="Jobs in flight">{formatNumber(stats.data.jobs_in_flight)}</Row>
          <Row label="Dead-letter">{formatNumber(stats.data.dead_letter_size)}</Row>
          <Row label="Worker concurrency">{formatNumber(stats.data.worker_concurrency)}</Row>
        </div>
      </CardContent>
    </Card>
  );
}
