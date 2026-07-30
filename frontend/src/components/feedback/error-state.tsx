"use client";

import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Inline error state for a failed data load, with an optional retry action.
 * Used by feature views wired to a query's `error`/`refetch`. Keeps the message
 * user-facing; verbose errors belong in the console/telemetry, not the UI.
 */
export function ErrorState({
  title = "Couldn't load this",
  message = "Something went wrong while loading. Please try again.",
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="border-destructive/30 bg-destructive/5 flex min-h-52 flex-col items-center justify-center gap-3 rounded-xl border p-10 text-center"
    >
      <div className="bg-destructive/10 text-destructive flex size-12 items-center justify-center rounded-full">
        <AlertTriangle className="size-6" aria-hidden />
      </div>
      <p className="text-sm font-medium">{title}</p>
      <p className="text-muted-foreground max-w-sm text-sm">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
