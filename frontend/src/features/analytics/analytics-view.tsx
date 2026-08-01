"use client";

import { Activity, Boxes, CopyCheck, Gauge, Search, Sparkles, Upload } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { DataTable, type Column } from "@/components/data/data-table";
import { StatCard } from "@/components/data/stat-card";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton, StatGridSkeleton } from "@/components/feedback/loading-skeletons";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  TREND_GRANULARITIES,
  TREND_METRICS,
  type TrendGranularity,
} from "@/lib/api/endpoints/analytics";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";
import { useState } from "react";

import {
  useAllTrends,
  useDashboardAnalytics,
  useModelAnalytics,
  usePipelineAnalytics,
  useRuntimeStats,
} from "./queries";
import { TrendChart } from "./trend-chart";

const METRIC_LABELS: Record<string, string> = {
  upload: "Uploads",
  search: "Searches",
  duplicate_check: "Duplicate checks",
  recommendation: "Recommendations",
};

const PERIOD_OPTIONS = ["7", "14", "30", "90"];

/** Usage counters for the window the backend reports. */
function UsageCards() {
  const { data, isPending, isError, refetch } = useDashboardAnalytics();

  if (isPending) return <StatGridSkeleton count={4} />;
  if (isError) {
    return <ErrorState title="Couldn't load usage metrics" onRetry={() => void refetch()} />;
  }

  const { window: win, today, window_days: windowDays } = data;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Searches"
        value={formatNumber(win.searches)}
        hint={`${formatNumber(today.searches)} today · ${windowDays}-day window`}
        icon={Search}
      />
      <StatCard
        label="Uploads"
        value={formatNumber(win.uploads)}
        hint={`${formatNumber(today.uploads)} today`}
        icon={Upload}
      />
      <StatCard
        label="Duplicate checks"
        value={formatNumber(win.duplicate_checks)}
        hint={`${formatNumber(today.duplicate_checks)} today`}
        icon={CopyCheck}
      />
      <StatCard
        label="Recommendations"
        value={formatNumber(win.recommendations)}
        hint={`${formatNumber(today.recommendations)} today`}
        icon={Sparkles}
      />
    </div>
  );
}

/**
 * Latency and throughput.
 *
 * `average_processing_seconds` is the one latency figure the analytics layer
 * exposes — it covers whole-request processing, not a per-stage split. Embedding
 * and retrieval are not separately timed in any JSON response, so no such
 * breakdown is shown; `/metrics` carries Prometheus histograms for that, and it
 * is not a UI data source.
 */
function ThroughputPanel() {
  const pipeline = usePipelineAnalytics();
  const stats = useRuntimeStats();

  if (pipeline.isPending || stats.isPending) return <CardSkeleton />;
  if (pipeline.isError) {
    return (
      <ErrorState title="Couldn't load pipeline metrics" onRetry={() => void pipeline.refetch()} />
    );
  }

  const usage = pipeline.data.usage;
  const runtime = stats.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Latency &amp; pipeline throughput</CardTitle>
        <CardDescription>
          {formatDate(pipeline.data.start_date)} – {formatDate(pipeline.data.end_date)}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Avg processing"
            value={`${formatNumber(usage.average_processing_seconds, { maximumFractionDigits: 2 })}s`}
            hint="Whole-request average"
            icon={Gauge}
          />
          {runtime ? (
            <>
              <StatCard
                label="Queue depth"
                value={formatNumber(runtime.queue_depth)}
                hint={`${formatNumber(runtime.jobs_in_flight)} in flight`}
                icon={Activity}
              />
              <StatCard
                label="Workers"
                value={formatNumber(runtime.worker_concurrency)}
                hint="Configured concurrency"
                icon={Activity}
              />
              <StatCard
                label="Dead letter"
                value={formatNumber(runtime.dead_letter_size)}
                hint="Jobs that exhausted retries"
                icon={Activity}
              />
            </>
          ) : null}
        </div>

        <p className="text-muted-foreground text-xs">
          The analytics layer reports one aggregate processing time. Per-stage embedding and
          retrieval latencies are not exposed by any JSON endpoint, so none are shown here — they
          live in the Prometheus exposition at <code className="text-xs">/metrics</code>.
        </p>
      </CardContent>
    </Card>
  );
}

/** Active and registered model versions. */
function ModelPanel() {
  const { data, isPending, isError, refetch } = useModelAnalytics();

  if (isPending) return <CardSkeleton />;
  if (isError) {
    return <ErrorState title="Couldn't load model analytics" onRetry={() => void refetch()} />;
  }

  // `models` has a server-side default, so it is optional in the generated
  // schema; treat a missing list as an empty one.
  const models = data.models ?? [];

  const columns: Column<(typeof models)[number]>[] = [
    { header: "Type", cell: (m) => <span className="font-mono text-xs">{m.model_type}</span> },
    { header: "Active model", cell: (m) => m.active_model ?? "—" },
    { header: "Version", cell: (m) => m.active_version ?? "—" },
    {
      header: "Status",
      cell: (m) => (m.status ? <Badge variant="outline">{m.status}</Badge> : "—"),
    },
    {
      header: "Registered",
      cell: (m) => <span className="tabular-nums">{formatNumber(m.registered_versions)}</span>,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Models in use ({models.length})</CardTitle>
        <CardDescription>Generated {formatDateTime(data.generated_at)}</CardDescription>
      </CardHeader>
      <CardContent>
        <DataTable
          rows={models}
          columns={columns}
          getRowKey={(m) => m.model_type}
          empty="No models are registered."
        />
      </CardContent>
    </Card>
  );
}

/**
 * AI analytics: usage, latency, throughput, model, and per-metric trends.
 *
 * Every number comes from `/analytics/*` and `/system/stats`. Each section
 * degrades on its own, so one unavailable endpoint (analytics is feature-gated)
 * does not blank the page.
 */
export function AnalyticsView() {
  const [granularity, setGranularity] = useState<TrendGranularity>("daily");
  const [periods, setPeriods] = useState("7");

  const trends = useAllTrends(granularity, Number(periods));
  const anyTrendError = trends.some((t) => t.isError);

  return (
    <>
      <PageHeader
        title="AI Analytics"
        description="Usage, latency, throughput, and model activity across the platform."
      />

      <div className="space-y-6">
        <UsageCards />

        <ThroughputPanel />

        <Card>
          <CardHeader className="flex flex-row flex-wrap items-end justify-between gap-4 space-y-0">
            <div>
              <CardTitle className="text-base">Event trends</CardTitle>
              <CardDescription>
                One series per countable event, exactly as the backend buckets them.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="a-granularity">Granularity</Label>
                <Select
                  value={granularity}
                  onValueChange={(v) => setGranularity(v as TrendGranularity)}
                >
                  <SelectTrigger id="a-granularity" className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TREND_GRANULARITIES.map((g) => (
                      <SelectItem key={g} value={g} className="capitalize">
                        {g}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="a-periods">Periods</Label>
                <Select value={periods} onValueChange={setPeriods}>
                  <SelectTrigger id="a-periods" className="w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PERIOD_OPTIONS.map((p) => (
                      <SelectItem key={p} value={p}>
                        Last {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {anyTrendError ? (
              <Alert>
                <Boxes className="size-4" aria-hidden="true" />
                <AlertTitle>Some trends could not be loaded</AlertTitle>
                <AlertDescription>
                  The charts below show whichever metrics did return. Analytics is feature-gated by
                  <code className="mx-1 text-xs">ANALYTICS__ENABLED</code>on the backend.
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="grid gap-4 xl:grid-cols-2">
              {TREND_METRICS.map((metric, index) => {
                const query = trends[index];
                if (query.isPending) return <CardSkeleton key={metric} />;
                if (query.isError || !query.data) return null;
                return (
                  <TrendChart
                    key={metric}
                    title={METRIC_LABELS[metric] ?? metric}
                    description={`${query.data.granularity} · ${query.data.points.length} periods`}
                    points={query.data.points}
                  />
                );
              })}
            </div>
          </CardContent>
        </Card>

        <ModelPanel />
      </div>
    </>
  );
}
