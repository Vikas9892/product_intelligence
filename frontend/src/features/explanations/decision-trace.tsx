import { Info } from "lucide-react";

import { ConfidenceBadge } from "@/components/data/confidence-badge";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ExplanationResponse } from "@/lib/api/types";
import { formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Human labels for the reason codes the backend emits. An unmapped code falls
 * back to the backend's own `description`, so a newly added code still renders
 * correctly rather than disappearing.
 */
const REASON_LABELS: Record<string, string> = {
  shared_brand: "Same brand",
  shared_category: "Same category",
  matched_attributes: "Matching attributes",
  shared_tags: "Shared tags",
  weighted_similarity: "Weighted similarity",
};

/** The structured evidence behind a decision. */
export function ReasonList({ explanation }: { explanation: ExplanationResponse }) {
  const reasons = explanation.reasons ?? [];
  if (reasons.length === 0) return null;

  return (
    <ul className="space-y-1.5">
      {reasons.map((reason) => (
        <li key={reason.code} className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <Badge variant="outline" className="font-mono text-[0.7rem]">
            {REASON_LABELS[reason.code] ?? reason.code}
          </Badge>
          <span className="text-muted-foreground">{reason.description}</span>
          {reason.weight !== null && reason.weight !== undefined ? (
            <span className="text-muted-foreground tabular-nums">
              (weight {formatScore(reason.weight)})
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/**
 * The weighted components behind a decision's score.
 *
 * Each component is rendered exactly as the backend reports it — `value`,
 * `weight`, and `contribution` — followed by the **aggregation step**: the sum
 * of the contributions, and the final score they produce.
 *
 * Showing the sum is the point. A reader must be able to follow the arithmetic
 * from components through to the final number; a panel whose figures visibly
 * do not close undermines the explainability it exists to provide. (Recommendation
 * traces previously published two of four components at a hardcoded weight of
 * 1.0, so a real response read "similarity 0.57, quality 0.64" against a final
 * of 0.51 — see `RecommendationExplainer`.)
 *
 * Where the sum does not equal the total, the difference is surfaced as its own
 * `Adjustment` line rather than quietly ignored: a clamp, cap or penalty applied
 * after the weighted sum is part of the reasoning and should be visible as such.
 */
export function ConfidenceBreakdown({ explanation }: { explanation: ExplanationResponse }) {
  const breakdown = explanation.breakdown;
  // `components` is optional in the generated schema (it has a server-side
  // default), so treat a missing list the same as an empty one.
  const components = breakdown?.components ?? [];
  if (!breakdown || components.length === 0) return null;

  const summed = components.reduce((running, component) => running + component.contribution, 0);
  // Tolerance covers float noise only. Anything larger is a real post-sum
  // adjustment (a clamp or penalty) and is shown as its own line.
  const residual = breakdown.total - summed;
  const hasAdjustment = Math.abs(residual) > 0.0005;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Score components
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label="How these components relate to the final score"
                className="text-muted-foreground hover:text-foreground"
              >
                <Info className="size-3.5" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              Each component&apos;s value, weight, and contribution as reported by the backend.
              Contribution is value × weight; the contributions add up to the final score. Any
              difference is shown separately as an adjustment.
            </TooltipContent>
          </Tooltip>
        </div>
        <span className="text-sm font-medium tabular-nums">
          Final {formatScore(breakdown.total)}
        </span>
      </div>

      <ul className="space-y-2.5">
        {components.map((component) => (
          <li key={component.name} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="capitalize">{component.name}</span>
              <span className="text-muted-foreground text-xs tabular-nums">
                value {formatScore(component.value)} · weight {formatScore(component.weight)} ·
                contribution {formatScore(component.contribution)}
              </span>
            </div>
            <Progress
              value={Math.max(0, Math.min(1, component.value)) * 100}
              aria-label={`${component.name} value ${formatScore(component.value)}`}
            />
          </li>
        ))}
      </ul>

      {/* The aggregation step, so the arithmetic visibly closes. */}
      <dl
        className="border-border/60 space-y-1 border-t pt-2.5 text-xs"
        aria-label="How the components aggregate to the final score"
      >
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-muted-foreground">Sum of contributions</dt>
          <dd className="tabular-nums">{formatScore(summed)}</dd>
        </div>
        {hasAdjustment && (
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-muted-foreground">Adjustment applied after weighting</dt>
            <dd className="tabular-nums">
              {residual > 0 ? "+" : "−"}
              {formatScore(Math.abs(residual))}
            </dd>
          </div>
        )}
        <div className="flex items-baseline justify-between gap-2 font-medium">
          <dt>Final score</dt>
          <dd className="tabular-nums">{formatScore(breakdown.total)}</dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * One complete decision trace: the backend's own summary, its confidence, the
 * structured reasons, and the weighted score components. Every field is
 * rendered from the response — nothing is inferred.
 */
export function DecisionTrace({
  explanation,
  className,
}: {
  explanation: ExplanationResponse;
  className?: string;
}) {
  const hasConfidence = explanation.confidence !== null && explanation.confidence !== undefined;

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-medium">{explanation.summary}</p>
        {hasConfidence ? <ConfidenceBadge score={explanation.confidence as number} /> : null}
      </div>
      <ReasonList explanation={explanation} />
      <ConfidenceBreakdown explanation={explanation} />
    </div>
  );
}
