"use client";

import { CircleCheck, CircleAlert, Info } from "lucide-react";

import { ConfidenceBadge } from "@/components/data/confidence-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DuplicateCheckResponse } from "@/lib/api/types";
import { formatScore } from "@/lib/format";

/**
 * The verdict itself: whether the backend judged this a duplicate, how
 * confident it was, and the reasons it gave.
 *
 * Meaning is carried by the icon and text, not colour alone. `reasons` (the
 * Phase-15 list) is preferred when present and falls back to the single
 * `reason` string, so the panel is correct whether or not cross-encoder
 * verification is enabled.
 */
export function VerdictPanel({ result }: { result: DuplicateCheckResponse }) {
  const reasons = result.reasons?.length ? result.reasons : [result.reason];

  return (
    <Alert variant={result.duplicate ? "destructive" : "default"}>
      {result.duplicate ? (
        <CircleAlert className="size-4" aria-hidden="true" />
      ) : (
        <CircleCheck className="size-4" aria-hidden="true" />
      )}
      <AlertTitle className="flex flex-wrap items-center gap-2">
        {result.duplicate ? "Duplicate detected" : "No duplicate detected"}
        <ConfidenceBadge score={result.confidence} />
      </AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-4">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

/**
 * Cross-encoder verification (Phase 15).
 *
 * `cross_encoder_score` and `retrieval_similarity` are populated **only** when
 * `DUPLICATE_VERIFICATION__ENABLED` is on; they are `null` otherwise, which is
 * the backend's default. This panel therefore reports the feature as disabled
 * rather than rendering a placeholder number — a null is a real, meaningful
 * state here, not missing data to paper over.
 */
export function CrossEncoderPanel({ result }: { result: DuplicateCheckResponse }) {
  const crossEncoder = result.cross_encoder_score;
  const retrieval = result.retrieval_similarity;
  const enabled = crossEncoder !== null && crossEncoder !== undefined;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          Cross-encoder verification
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label="About cross-encoder verification"
                className="text-muted-foreground hover:text-foreground"
              >
                <Info className="size-3.5" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              A second-stage transformer that re-scores the best candidate directly against the
              submitted product, rather than comparing embeddings. The backend runs it only when
              DUPLICATE_VERIFICATION__ENABLED is on.
            </TooltipContent>
          </Tooltip>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {enabled ? (
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground text-xs tracking-wide uppercase">
                Cross-encoder score
              </dt>
              <dd className="text-lg font-medium tabular-nums">{formatScore(crossEncoder, 4)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs tracking-wide uppercase">
                Retrieval similarity
              </dt>
              <dd className="text-lg font-medium tabular-nums">
                {retrieval !== null && retrieval !== undefined ? formatScore(retrieval, 4) : "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <div className="space-y-2">
            <Badge variant="outline">Disabled on this backend</Badge>
            <p className="text-muted-foreground text-sm">
              The backend returned no cross-encoder score, which means
              <code className="mx-1 text-xs">DUPLICATE_VERIFICATION__ENABLED</code>
              is off. The verdict above comes from the weighted similarity signals alone. No score
              is shown here because none was produced.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
