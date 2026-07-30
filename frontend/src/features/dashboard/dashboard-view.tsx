"use client";

import { PageHeader } from "@/components/common/page-header";

import { MetricsCards } from "./metrics-cards";
import { PipelinePanel } from "./pipeline-panel";
import { SystemPanel } from "./system-panel";

/**
 * Dashboard composition. Each section owns its query, loading skeleton, and
 * error state, so one failing endpoint never blanks the whole page — a
 * degraded-but-useful dashboard. All data is real backend output; there is no
 * mocked activity feed because the backend exposes no per-item history.
 */
export function DashboardView() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Live catalog activity, pipeline throughput, and system health."
      />
      <MetricsCards />
      <div className="grid gap-4 lg:grid-cols-2">
        <SystemPanel />
        <PipelinePanel />
      </div>
    </>
  );
}
