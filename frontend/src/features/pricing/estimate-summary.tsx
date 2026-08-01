"use client";

import { Info, Scissors } from "lucide-react";

import { ConfidenceBadge, type ConfidenceLevel } from "@/components/data/confidence-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { PricingResponse } from "@/lib/api/types";
import { formatPrice } from "@/lib/format";

import { computeSpread, CONFIDENCE_EXPLANATION, STRATEGY_EXPLANATION } from "./spread";

/** The backend's `confidence` string mapped onto the shared badge's levels. */
function asLevel(confidence: string): ConfidenceLevel {
  return confidence === "high" || confidence === "medium" ? confidence : "low";
}

/**
 * The headline estimate.
 *
 * `estimated_price`, `confidence`, `confidence_score`, `strategy`,
 * `comparable_count`, and `pricing_reason` are all rendered verbatim from the
 * response. The min/median/max line is explicitly labelled as a summary of the
 * returned comparables — a description of the list, never a competing estimate.
 */
export function EstimateSummary({ result }: { result: PricingResponse }) {
  const spread = computeSpread(result.comparables ?? [], result.estimated_price);
  const noComparables = (result.comparables?.length ?? 0) === 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Estimated price</CardTitle>
        <CardDescription>{result.pricing_reason}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div>
            <p className="text-4xl font-semibold tabular-nums">
              {formatPrice(result.estimated_price)}
            </p>
            {noComparables ? (
              <p className="text-muted-foreground mt-1 text-sm">
                The backend found nothing priced to compare against, so it returned 0.00 at low
                confidence — this is not a real valuation.
              </p>
            ) : null}
          </div>

          <div className="space-y-1">
            <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Confidence
            </span>
            <div className="flex items-center gap-2">
              <ConfidenceBadge level={asLevel(result.confidence)} score={result.confidence_score} />
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="What drives this confidence level"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Info className="size-3.5" aria-hidden="true" />
                  </button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  {CONFIDENCE_EXPLANATION[result.confidence] ??
                    "Confidence level as reported by the backend."}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>

          <div className="space-y-1">
            <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Strategy
            </span>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="font-mono">
                {result.strategy}
              </Badge>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="How this strategy aggregates comparables"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Info className="size-3.5" aria-hidden="true" />
                  </button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  {STRATEGY_EXPLANATION[result.strategy] ??
                    "Aggregation strategy as reported by the backend."}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>

          <div className="space-y-1">
            <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Comparables used
            </span>
            <p className="text-lg font-medium tabular-nums">{result.comparable_count}</p>
          </div>
        </div>

        {spread ? (
          <dl className="grid grid-cols-3 gap-3 border-t pt-4">
            <div>
              <dt className="text-muted-foreground text-xs tracking-wide uppercase">Lowest</dt>
              <dd className="font-medium tabular-nums">{formatPrice(spread.min)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs tracking-wide uppercase">Median</dt>
              <dd className="font-medium tabular-nums">{formatPrice(spread.median)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs tracking-wide uppercase">Highest</dt>
              <dd className="font-medium tabular-nums">{formatPrice(spread.max)}</dd>
            </div>
            <p className="text-muted-foreground col-span-3 text-xs">
              Summary of the {spread.count} comparable{spread.count === 1 ? "" : "s"} in this
              response, computed here for context. The estimate above is the backend&apos;s.
            </p>
          </dl>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * How outliers were handled.
 *
 * The backend removes outliers with a Tukey IQR fence *before* building the
 * response, so the returned `comparables` are the survivors and the discarded
 * prices are not in the payload at all. That is stated plainly rather than
 * implying the UI could highlight them — and no client-side outlier detection
 * is run, because re-deriving one could contradict the backend's own decision.
 */
export function OutlierNote({ result }: { result: PricingResponse }) {
  const kept = result.comparables?.length ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Scissors className="size-4" aria-hidden="true" />
          Outlier handling
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>
          Before aggregating, the backend drops comparables outside a Tukey IQR fence (
          <code className="text-xs">PRICING__OUTLIER_IQR_MULTIPLIER</code>, 1.5 by default), then
          applies <span className="font-mono">{result.strategy}</span> to what survives.
        </p>
        <p className="text-muted-foreground">
          The {kept} comparable{kept === 1 ? "" : "s"} shown are those survivors. Discarded prices
          are removed server-side and are not part of the response, so they cannot be listed here —
          and no outlier detection is re-run in the browser, which could disagree with the
          backend&apos;s own decision.
        </p>
        {result.comparable_count !== kept ? (
          <p className="text-muted-foreground">
            The backend reports {result.comparable_count} used against {kept} returned.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
