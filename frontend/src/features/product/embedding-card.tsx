"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { formatNumber } from "@/lib/format";

import { useModels } from "./queries";

/**
 * Embedding summary. Raw vectors are never exposed by the API by design, so
 * this shows which models produced this product's embeddings and their
 * dimensions, read from the model registry.
 */
export function EmbeddingCard() {
  const { data, isPending, isError } = useModels();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Embeddings</CardTitle>
        <CardDescription>Models used to index this product</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <CardSkeleton />
        ) : isError || !data ? (
          <p className="text-muted-foreground text-sm">Model information is unavailable.</p>
        ) : (
          <div className="space-y-2">
            {data.map((model) => (
              <div
                key={`${model.model_type}-${model.version}`}
                className="flex items-center justify-between gap-4 border-b py-2 text-sm last:border-b-0"
              >
                <div>
                  <div className="font-medium capitalize">{model.model_type}</div>
                  <div className="text-muted-foreground font-mono text-xs">{model.model_name}</div>
                </div>
                <div className="text-right">
                  <div className="tabular-nums">{formatNumber(model.dimension)}-d</div>
                  <div className="text-muted-foreground text-xs">v{model.version}</div>
                </div>
              </div>
            ))}
            <p className="text-muted-foreground pt-1 text-xs">
              Vector values are not exposed by the API.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
