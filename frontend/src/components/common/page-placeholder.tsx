import type { LucideIcon } from "lucide-react";

/**
 * Placeholder body for a page whose feature is implemented in a later stage.
 * Communicates that the route exists and is wired up, without any mocked data
 * or fake functionality. Replaced by the real feature UI in its own stage.
 */
export function PagePlaceholder({ icon: Icon, stage }: { icon: LucideIcon; stage: string }) {
  return (
    <div className="border-border/60 flex min-h-64 flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-10 text-center">
      <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-full">
        <Icon className="size-6" />
      </div>
      <p className="text-sm font-medium">This section is not built yet</p>
      <p className="text-muted-foreground max-w-sm text-sm">
        The layout and navigation are in place. The functionality for this page arrives in {stage}.
      </p>
    </div>
  );
}
