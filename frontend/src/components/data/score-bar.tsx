import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

/**
 * Horizontal similarity/score meter for a 0..1 value (search relevance,
 * duplicate signals). Optionally labeled with the numeric value. Clamps out-of
 * range input defensively.
 */
export function ScoreBar({
  value,
  label,
  className,
}: {
  value: number;
  label?: string;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(1, value));
  const pct = Math.round(clamped * 100);

  return (
    <div className={cn("space-y-1", className)}>
      {label ? (
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{label}</span>
          <span className="font-medium tabular-nums">{clamped.toFixed(2)}</span>
        </div>
      ) : null}
      <Progress value={pct} aria-label={label ?? "score"} />
    </div>
  );
}
