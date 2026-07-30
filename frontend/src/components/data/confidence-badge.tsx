import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ConfidenceLevel = "low" | "medium" | "high";

/** Maps a 0..1 score to a coarse confidence level. */
export function levelFromScore(score: number): ConfidenceLevel {
  if (score >= 0.75) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

const STYLES: Record<ConfidenceLevel, string> = {
  high: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  medium: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
  low: "border-transparent bg-muted text-muted-foreground",
};

const LABELS: Record<ConfidenceLevel, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

/**
 * Confidence indicator used across duplicate, pricing, and recommendation
 * results. Accepts an explicit `level` or a raw `score` (0..1); when a score is
 * given it is shown alongside the level. Level text carries the meaning, not
 * color alone.
 */
export function ConfidenceBadge({
  level,
  score,
  className,
}: {
  level?: ConfidenceLevel;
  score?: number;
  className?: string;
}) {
  const resolved = level ?? (score !== undefined ? levelFromScore(score) : "low");
  return (
    <Badge className={cn(STYLES[resolved], "tabular-nums", className)}>
      {LABELS[resolved]}
      {score !== undefined ? ` · ${score.toFixed(2)}` : null}
    </Badge>
  );
}
