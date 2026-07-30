"use client";

import { AlertTriangle, Check, Loader2 } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { JobStatusResponse } from "@/lib/api/types";

/**
 * Visualizes a processing job's progress. The four steps mirror the backend
 * worker's real checkpoints (Validating → Processing → Recommendations →
 * Complete); the worker reports coarse progress (10/40/80/100) around one
 * pipeline call, so the live `current_stage` text is shown for detail rather
 * than fabricating finer sub-steps.
 */
const STEPS = [
  { label: "Queued", threshold: 0 },
  { label: "Processing", threshold: 10 },
  { label: "Recommendations", threshold: 80 },
  { label: "Complete", threshold: 100 },
] as const;

export function JobProgress({ job }: { job: JobStatusResponse }) {
  const failed = job.status === "failed";

  return (
    <div className="space-y-5">
      <ol className="flex items-center gap-2">
        {STEPS.map((step, index) => {
          const reached = job.progress >= step.threshold && !failed;
          const isCurrent =
            !failed &&
            job.progress >= step.threshold &&
            (index === STEPS.length - 1 || job.progress < STEPS[index + 1].threshold);
          return (
            <li key={step.label} className="flex flex-1 flex-col items-center gap-1.5 text-center">
              <div
                className={cn(
                  "flex size-8 items-center justify-center rounded-full border text-xs font-medium",
                  reached
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border text-muted-foreground",
                )}
              >
                {job.progress >= 100 && index === STEPS.length - 1 ? (
                  <Check className="size-4" />
                ) : isCurrent && job.status === "running" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  index + 1
                )}
              </div>
              <span className={cn("text-xs", reached ? "font-medium" : "text-muted-foreground")}>
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>

      <Progress value={job.progress} aria-label="Processing progress" />

      <div aria-live="polite" className="text-muted-foreground text-sm">
        {failed ? (
          <span className="text-destructive inline-flex items-center gap-1.5">
            <AlertTriangle className="size-4" />
            {job.error ?? "Processing failed."}
          </span>
        ) : (
          <span>
            {job.current_stage} · {job.progress}%
          </span>
        )}
      </div>
    </div>
  );
}
