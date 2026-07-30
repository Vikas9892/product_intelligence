"use client";

import { ShieldCheck } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge } from "@/components/data/confidence-badge";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import type { ExplanationResponse } from "@/lib/api/types";

import { useExplanations } from "./queries";

function Reasons({ explanation }: { explanation: ExplanationResponse }) {
  const reasons = explanation.reasons ?? [];
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <p className="text-sm font-medium">{explanation.summary}</p>
        {explanation.confidence !== null && explanation.confidence !== undefined ? (
          <ConfidenceBadge score={explanation.confidence} />
        ) : null}
      </div>
      {reasons.length > 0 ? (
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm">
          {reasons.map((reason) => (
            <li key={reason.code}>{reason.description}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Duplicate decision and explainability for this product, from
 * GET /products/{id}/explanations. Shows the duplicate trace (verdict,
 * confidence, human-readable reasons) and how many recommendation traces exist.
 */
export function ExplainabilityCard({ id }: { id: string }) {
  const { data, isPending, isError, refetch } = useExplanations(id);
  const recExplanationCount = data?.recommendations?.length ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Duplicate & explainability</CardTitle>
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
                <Reasons explanation={data.duplicate} />
              ) : (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <ShieldCheck className="size-4" /> No duplicate decision is recorded for this
                  product.
                </p>
              )}
            </div>

            {recExplanationCount > 0 ? (
              <p className="text-muted-foreground border-t pt-3 text-sm">
                {recExplanationCount} recommendation explanation
                {recExplanationCount === 1 ? "" : "s"} available.
              </p>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
