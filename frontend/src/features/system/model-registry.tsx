"use client";

import { Activity } from "lucide-react";

import { DataTable, type Column } from "@/components/data/data-table";
import { StatusBadge } from "@/components/data/status-badge";
import { ErrorState } from "@/components/feedback/error-state";
import { StatGridSkeleton } from "@/components/feedback/loading-skeletons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useModels } from "@/features/product/queries";
import type { ModelInfoResponse } from "@/lib/api/types";
import { formatDateTime, formatNumber } from "@/lib/format";

/** The model registry, from `GET /models`. */
export function ModelRegistry() {
  const models = useModels();

  const columns: Column<ModelInfoResponse>[] = [
    {
      header: "Model",
      cell: (m) => (
        <div className="min-w-48">
          <div className="font-medium">{m.model_name}</div>
          <div className="text-muted-foreground font-mono text-xs">{m.model_type}</div>
        </div>
      ),
    },
    { header: "Version", cell: (m) => <span className="tabular-nums">{m.version}</span> },
    {
      header: "Status",
      cell: (m) => (
        <StatusBadge tone={m.status === "active" ? "success" : "neutral"}>{m.status}</StatusBadge>
      ),
    },
    {
      header: "Dimension",
      cell: (m) => <span className="tabular-nums">{formatNumber(m.dimension)}</span>,
    },
    { header: "Provider", cell: (m) => m.provider },
    { header: "Registered", cell: (m) => formatDateTime(m.created_at) },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="size-4" aria-hidden="true" />
          Model registry
        </CardTitle>
        <CardDescription>Models the platform has registered and their status.</CardDescription>
      </CardHeader>
      <CardContent>
        {models.isPending ? (
          <StatGridSkeleton count={3} />
        ) : models.isError ? (
          <ErrorState
            title="Couldn't load the model registry"
            onRetry={() => void models.refetch()}
          />
        ) : (
          <DataTable
            rows={models.data ?? []}
            columns={columns}
            getRowKey={(m) => `${m.model_type}-${m.model_name}`}
            empty="No models are registered."
          />
        )}
      </CardContent>
    </Card>
  );
}
