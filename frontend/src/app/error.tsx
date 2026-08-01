"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary (Next.js `error.tsx`). Catches render/data errors
 * in the segment below it and offers a recovery action. Client component by
 * requirement. Detailed errors are logged to the console, never shown to the
 * user verbatim.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="bg-destructive/10 text-destructive flex size-12 items-center justify-center rounded-full">
        <AlertTriangle className="size-6" />
      </div>
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Something went wrong</h2>
        <p className="text-muted-foreground max-w-md text-sm">
          An unexpected error occurred while rendering this page. You can try again.
        </p>
        {error.digest ? (
          /*
           * The digest is an opaque id Next assigns to the server-side error —
           * it carries no message or stack, so it is safe to display, and it is
           * the only thing that lets a reported problem be matched to a log
           * line. Without it a bug report is just "it broke".
           */
          <p className="text-muted-foreground pt-1 font-mono text-xs">Reference: {error.digest}</p>
        ) : null}
      </div>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
