"use client";

import { CircleCheck, CircleSlash, HelpCircle, Info, Server, TriangleAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState } from "@/components/feedback/error-state";
import { RowsSkeleton } from "@/components/feedback/loading-skeletons";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useSystemHealth, useSystemStats } from "@/features/dashboard/queries";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ModelRegistry } from "./model-registry";
import {
  overallStatus,
  queueDepthIsMeaningful,
  STATUS_LABEL,
  toStatus,
  type OperationalStatus,
} from "./status";

const STATUS_STYLE: Record<OperationalStatus, { icon: LucideIcon; className: string }> = {
  healthy: {
    icon: CircleCheck,
    className: "border-transparent bg-success-soft text-success-foreground",
  },
  unhealthy: {
    icon: TriangleAlert,
    className: "border-transparent bg-danger-soft text-danger-foreground",
  },
  unknown: { icon: HelpCircle, className: "border-transparent bg-muted text-muted-foreground" },
  disabled: { icon: CircleSlash, className: "border-transparent bg-muted text-muted-foreground" },
};

/** Status pill. Meaning is carried by icon + text, never colour alone. */
function StatusPill({ status }: { status: OperationalStatus }) {
  const style = STATUS_STYLE[status];
  const Icon = style.icon;
  return (
    <Badge className={cn("gap-1", style.className)}>
      <Icon className="size-3" aria-hidden="true" />
      {STATUS_LABEL[status]}
    </Badge>
  );
}

/** One labelled row with an optional explanatory tooltip. */
function OpsRow({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2.5 last:border-b-0">
      <span className="flex items-center gap-1.5 text-sm">
        {label}
        {hint ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`About ${label}`}
                className="text-muted-foreground hover:text-foreground"
              >
                <Info className="size-3.5" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">{hint}</TooltipContent>
          </Tooltip>
        ) : null}
      </span>
      <span className="text-sm font-medium tabular-nums">{value}</span>
    </div>
  );
}

/**
 * The operations panel.
 *
 * Two backend behaviors shape this directly:
 *
 * 1. `workers` is the **configured concurrency**, not a live process count.
 *    The service's own docstring says so: the API has no handle on the worker
 *    processes, and a real liveness count would need heartbeats it does not
 *    implement. It is therefore labelled "Configured workers" and never
 *    presented as how many workers are running.
 * 2. Every dependency read degrades to `unhealthy`/`0` instead of raising. So a
 *    queue depth of 0 while Redis is unhealthy is a fallback, not a
 *    measurement, and is reported as unknown.
 */
function OperationsPanel() {
  const health = useSystemHealth();
  const stats = useSystemStats();

  if (health.isPending || stats.isPending) {
    // The card chrome renders immediately and the placeholder reserves the
    // height of all ten rows, so nothing below this panel moves when the data
    // arrives. Previously a three-line CardSkeleton stood in for a ten-row
    // panel, which was the bulk of this route's layout shift.
    return (
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="size-4" aria-hidden="true" />
              System operations
            </CardTitle>
            <CardDescription>Point-in-time snapshot, refreshed every 30 seconds.</CardDescription>
          </div>
          <Skeleton className="h-5 w-36" />
        </CardHeader>
        <CardContent>
          <RowsSkeleton rows={10} />
        </CardContent>
      </Card>
    );
  }
  if (health.isError) {
    return (
      <ErrorState
        title="Couldn't reach the system health endpoint"
        onRetry={() => void health.refetch()}
      />
    );
  }

  const redis = toStatus(health.data.redis);
  const qdrant = toStatus(health.data.qdrant);
  // A body arrived, so the API answered. That is the only thing this proves.
  const api: OperationalStatus = "healthy";
  const overall = overallStatus([api, redis, qdrant]);
  const queueTrustworthy = queueDepthIsMeaningful(redis);

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Server className="size-4" aria-hidden="true" />
            System operations
          </CardTitle>
          <CardDescription>Point-in-time snapshot, refreshed every 30 seconds.</CardDescription>
        </div>
        <Badge
          className={cn(
            "gap-1",
            overall === "operational"
              ? "bg-success-soft text-success-foreground border-transparent"
              : overall === "degraded"
                ? "bg-warning-soft text-warning-foreground border-transparent"
                : "bg-muted text-muted-foreground border-transparent",
          )}
        >
          {overall === "operational"
            ? "All systems operational"
            : overall === "degraded"
              ? "Degraded"
              : "Unknown"}
        </Badge>
      </CardHeader>

      <CardContent>
        <OpsRow
          label="API"
          value={<StatusPill status={api} />}
          hint="The health endpoint returned a response, so the API is serving. It reports dependency failures in the body with HTTP 200 rather than as an error status."
        />
        <OpsRow label="Redis" value={<StatusPill status={redis} />} />
        <OpsRow label="Qdrant" value={<StatusPill status={qdrant} />} />

        <OpsRow
          label="Queue depth"
          value={
            queueTrustworthy ? (
              formatNumber(health.data.queue_depth)
            ) : (
              <StatusPill status="unknown" />
            )
          }
          hint={
            queueTrustworthy
              ? "Jobs waiting in the Redis-backed processing queue."
              : "The queue lives in Redis, which is unavailable. The backend degrades a failed read to 0, so no depth can be reported right now."
          }
        />

        <OpsRow
          label="Configured workers"
          value={formatNumber(health.data.workers)}
          hint="The configured worker concurrency — NOT a count of running worker processes. The API has no handle on the worker pool and the backend implements no worker heartbeat, so live worker count is not knowable from here."
        />

        <OpsRow label="Active models" value={formatNumber(health.data.active_models)} />
        <OpsRow label="Uptime" value={health.data.uptime} />

        {stats.data ? (
          <>
            <OpsRow
              label="Jobs in flight"
              value={
                queueTrustworthy ? (
                  formatNumber(stats.data.jobs_in_flight)
                ) : (
                  <StatusPill status="unknown" />
                )
              }
            />
            <OpsRow
              label="Dead-lettered jobs"
              value={
                queueTrustworthy ? (
                  formatNumber(stats.data.dead_letter_size)
                ) : (
                  <StatusPill status="unknown" />
                )
              }
              hint="Jobs that exhausted their retries."
            />
            <OpsRow label="Registered models" value={formatNumber(stats.data.registered_models)} />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * System operations centre.
 *
 * Everything here comes from `/system/health`, `/system/stats`, and `/models`.
 * The Prometheus text at `/metrics` is deliberately not parsed: the frontend
 * architecture excludes it as a UI data source, and scraping domain metrics out
 * of an exposition format would invent structure the JSON API does not offer.
 */
export function SystemView() {
  return (
    <>
      <PageHeader
        title="System"
        description="Operational health, runtime statistics, and the model registry."
      />
      <div className="space-y-6">
        <OperationsPanel />
        <ModelRegistry />
        <p className="text-muted-foreground text-xs">
          Raw Prometheus metrics are exposed at <code className="text-xs">/metrics</code> for a
          scraper. They are not read here — the operational figures above come from the JSON system
          endpoints.
        </p>
      </div>
    </>
  );
}
