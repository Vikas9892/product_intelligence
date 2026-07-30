"use client";

import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
  const queryClient = useQueryClient();
  const fetching =
    useIsFetching({ queryKey: ["analytics"] }) + useIsFetching({ queryKey: ["system"] });

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["analytics"] });
    void queryClient.invalidateQueries({ queryKey: ["system"] });
  }

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Live catalog activity, pipeline throughput, and system health."
        actions={
          <Button variant="outline" size="sm" onClick={refresh} disabled={fetching > 0}>
            <RefreshCw className={cn("size-4", fetching > 0 && "animate-spin")} />
            Refresh
          </Button>
        }
      />
      <MetricsCards />
      <div className="grid gap-4 lg:grid-cols-2">
        <SystemPanel />
        <PipelinePanel />
      </div>
    </>
  );
}
