import { Gauge } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { LatencySource } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Retrieval latency for the last search.
 *
 * The distinction between a server- and client-measured number is surfaced
 * rather than hidden: `server` is the backend's own `X-Response-Time-Ms`
 * (handler time, no network), while `client` is a browser round trip used only
 * when that header is unreadable. The label always says which one is shown, so
 * the figure is never overstated as backend time when it isn't.
 */
export function LatencyBadge({
  latencyMs,
  source,
  className,
}: {
  latencyMs: number;
  source: LatencySource;
  className?: string;
}) {
  const isServer = source === "server";
  const label = `${Math.round(latencyMs)} ms`;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={cn("gap-1.5 tabular-nums", className)}
          aria-label={`Retrieval latency ${label}, ${isServer ? "measured by the backend" : "measured in the browser"}`}
        >
          <Gauge className="size-3.5" aria-hidden="true" />
          {label}
          <span className="text-muted-foreground font-normal">
            {isServer ? "backend" : "round trip"}
          </span>
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        {isServer
          ? "Measured by the backend (X-Response-Time-Ms): time spent handling the search, excluding network transfer."
          : "Measured in the browser: full round trip including network. The backend timing header was not readable for this request."}
      </TooltipContent>
    </Tooltip>
  );
}
