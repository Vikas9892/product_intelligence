"use client";

import { ShieldCheck } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { DecisionTrace } from "@/features/explanations/decision-trace";
import { useProductExplanations } from "@/features/explanations/queries";

/**
 * Duplicate decision and explainability for this product, from
 * `GET /products/{id}/explanations`.
 *
 * Rendering is delegated to the shared `DecisionTrace`, so this view, the
 * search workspace, and the duplicate/recommendation views present a trace
 * identically — including the weighted score components, which this card
 * previously discarded.
 */
export function ExplainabilityCard({ id }: { id: string }) {
  const { data, isPending, isError, refetch } = useProductExplanations(id);
  const recommendationTraces = data?.recommendations ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Duplicate &amp; explainability</CardTitle>
        <CardDescription>Why the system decided what it did</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <CardSkeleton />
        ) : isError ? (
          <ErrorState title="Couldn't load explanations" onRetry={() => void refetch()} />
        ) : (
          <div className="space-y-4">
            <div>
              <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
                Duplicate status
              </p>
              {data.duplicate ? (
                <DecisionTrace explanation={data.duplicate} />
              ) : (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <ShieldCheck className="size-4" aria-hidden="true" /> No duplicate decision is
                  recorded for this product.
                </p>
              )}
            </div>

            {recommendationTraces.length > 0 ? (
              <div className="space-y-3 border-t pt-3">
                <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                  Recommendation decisions ({recommendationTraces.length})
                </p>
                {recommendationTraces.map((trace, index) => (
                  <DecisionTrace
                    key={`${trace.subject_id ?? "trace"}-${index}`}
                    explanation={trace}
                    className="border-l-2 pl-3"
                  />
                ))}
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
