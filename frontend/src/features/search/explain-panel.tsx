"use client";

import { ChevronDown, Info, Sparkles } from "lucide-react";
import { useState } from "react";

import { ErrorState } from "@/components/feedback/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DecisionTrace } from "@/features/explanations/decision-trace";
import { useProductExplanations } from "@/features/explanations/queries";
import type { ProductSearchResult } from "@/lib/api/types";
import { formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";

/** What each modality means in terms of the model that produced the match. */
const MODALITY_EXPLANATION: Record<string, string> = {
  image: "The product image embedding (CLIP) matched the query image.",
  text: "The product text embedding (BGE) matched the query text.",
};

/**
 * Fields the search endpoint deliberately does not return per result.
 *
 * Listing them is the honest alternative to inventing them: `ProductSearchResult`
 * carries only `product_id`, `score`, `matched_modalities`, and `metadata`
 * (see `backend/app/schemas/search.py`), and the backend is frozen. Rather than
 * synthesize a per-modality split, the UI says where each figure genuinely
 * lives so it can be found rather than guessed at.
 */
const NOT_RETURNED: { label: string; where: string }[] = [
  {
    label: "Per-modality sub-scores",
    where:
      "Image and text similarity are fused server-side; the endpoint returns only the fused score.",
  },
  {
    label: "Cross-encoder score",
    where: "Reported by duplicate verification, not by search. See Duplicate Intelligence.",
  },
];

function WhyRetrieved({ result }: { result: ProductSearchResult }) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
          Why this was retrieved
        </p>
        {result.matched_modalities.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            The backend reported no matched modality for this result.
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {result.matched_modalities.map((modality) => (
              <li key={modality} className="text-muted-foreground">
                <span className="text-foreground font-medium capitalize">{modality}</span>
                {" — "}
                {MODALITY_EXPLANATION[modality] ?? "Reported by the backend as a matched modality."}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Fused relevance score
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label="About the fused relevance score"
                className="text-muted-foreground hover:text-foreground"
              >
                <Info className="size-3.5" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              The single relevance value the search endpoint returns. Image and text signals are
              combined on the server by its configured weights; the individual sides are not part of
              the response.
            </TooltipContent>
          </Tooltip>
        </div>
        <span className="text-sm font-medium tabular-nums">{formatScore(result.score, 4)}</span>
      </div>
    </div>
  );
}

function NotReturnedNote() {
  return (
    <div className="space-y-1.5">
      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        Not returned by this endpoint
      </p>
      <ul className="space-y-1">
        {NOT_RETURNED.map((item) => (
          <li key={item.label} className="flex flex-wrap items-baseline gap-x-2 text-sm">
            <Badge variant="outline" className="text-muted-foreground text-[0.7rem]">
              {item.label}
            </Badge>
            <span className="text-muted-foreground">{item.where}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Per-result explainability.
 *
 * Splits cleanly into what the search response itself carries (matched
 * modalities, fused score) and the product's recorded decision traces from
 * `GET /products/{id}/explanations` — which is where genuine weighted
 * breakdowns, reason codes, and confidence values live. The traces are fetched
 * only when the panel is opened, so a page of results does not trigger one
 * request per hit.
 */
export function ExplainPanel({
  result,
  className,
}: {
  result: ProductSearchResult;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const explanations = useProductExplanations(result.product_id, { enabled: open });

  const traces = explanations.data;
  const recommendationTraces = traces?.recommendations ?? [];
  const contentId = `explain-${result.product_id}`;

  return (
    <div className={cn("border-t pt-3", className)}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="w-full justify-between px-2"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-2">
          <Sparkles className="size-4" aria-hidden="true" />
          Why this result?
        </span>
        <ChevronDown
          className={cn("size-4 transition-transform", open && "rotate-180")}
          aria-hidden="true"
        />
      </Button>

      {open ? (
        <div id={contentId} className="space-y-4 px-2 pt-3">
          <WhyRetrieved result={result} />

          <Separator />

          <div className="space-y-3">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Recorded decisions for this product
            </p>

            {explanations.isPending ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-2 w-full" />
              </div>
            ) : explanations.isError ? (
              <ErrorState
                title="Couldn't load explanations"
                onRetry={() => void explanations.refetch()}
              />
            ) : (
              <div className="space-y-4">
                {traces?.duplicate ? (
                  <div className="space-y-2">
                    <Badge variant="outline">Duplicate decision</Badge>
                    <DecisionTrace explanation={traces.duplicate} />
                  </div>
                ) : null}

                {recommendationTraces.length > 0 ? (
                  <div className="space-y-3">
                    <Badge variant="outline">
                      {recommendationTraces.length} recommendation decision
                      {recommendationTraces.length === 1 ? "" : "s"}
                    </Badge>
                    {recommendationTraces.map((trace, index) => (
                      <DecisionTrace
                        key={`${trace.subject_id ?? "trace"}-${index}`}
                        explanation={trace}
                        className="border-l-2 pl-3"
                      />
                    ))}
                  </div>
                ) : null}

                {!traces?.duplicate && recommendationTraces.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    The backend has no recorded decision traces for this product yet. Traces are
                    written when it is processed for duplicates and recommendations.
                  </p>
                ) : null}
              </div>
            )}
          </div>

          <Separator />

          <NotReturnedNote />
        </div>
      ) : null}
    </div>
  );
}
