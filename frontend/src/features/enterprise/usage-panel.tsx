"use client";

import { Gauge, Info, TriangleAlert } from "lucide-react";

import { ForbiddenState } from "@/components/auth/permission";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import type { UsageResponse } from "@/lib/api/types";
import { formatNumber, formatPercent } from "@/lib/format";

import { useUsage } from "./queries";

/** A quota of 0 disables the ceiling entirely (backend convention). */
function quotaDisabled(limit: number): boolean {
  return limit === 0;
}

/**
 * Consumption of the daily quota.
 *
 * Both numbers come from the response — `requests_today` and
 * `daily_request_quota` — so the ratio is a faithful reading of what the
 * backend reported, not a derived estimate. A quota of `0` means no ceiling is
 * configured, which is shown as such rather than as "0% used" or a divide-by-
 * zero bar.
 */
function QuotaMeter({ usage }: { usage: UsageResponse }) {
  const disabled = quotaDisabled(usage.daily_request_quota);
  const ratio = disabled ? 0 : Math.min(1, usage.requests_today / usage.daily_request_quota);
  const exhausted = !disabled && usage.requests_today >= usage.daily_request_quota;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Daily requests
        </span>
        <span className="text-sm tabular-nums">
          {formatNumber(usage.requests_today)}
          {disabled ? (
            <span className="text-muted-foreground"> · no daily ceiling configured</span>
          ) : (
            <>
              {" / "}
              {formatNumber(usage.daily_request_quota)}
              <span className="text-muted-foreground"> ({formatPercent(ratio)})</span>
            </>
          )}
        </span>
      </div>

      {disabled ? null : (
        <Progress
          value={ratio * 100}
          aria-label={`${formatNumber(usage.requests_today)} of ${formatNumber(usage.daily_request_quota)} daily requests used`}
        />
      )}

      {exhausted ? (
        <Alert variant="destructive">
          <TriangleAlert className="size-4" aria-hidden="true" />
          <AlertTitle>Daily quota exhausted</AlertTitle>
          <AlertDescription>
            This tenant has used its full daily allowance. Further requests are rejected with 429
            until the counter resets.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}

/**
 * Tenant usage and the configured limits.
 *
 * `GET /usage` returns a **snapshot** — a requests-today counter plus the two
 * configured ceilings. There is no historical series behind it, so this panel
 * deliberately renders no chart: manufacturing a trend from a single point
 * would invent data the backend does not have.
 *
 * `rate_limit_per_minute` is likewise the *configured* ceiling. The backend
 * exposes no current-rate or remaining-budget field, so it is labelled as a
 * limit and never presented as live rate-limit state.
 */
export function UsagePanel() {
  const usage = useUsage();
  const forbidden = usage.error instanceof ApiError && usage.error.status === 403;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Gauge className="size-4" aria-hidden="true" />
          Usage &amp; quota
        </CardTitle>
        <CardDescription>Current consumption against this tenant&apos;s limits.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {usage.isPending ? (
          <CardSkeleton />
        ) : forbidden ? (
          <ForbiddenState capability="viewUsage" title="This key can't view usage" />
        ) : usage.isError ? (
          <ErrorState title="Couldn't load usage" onRetry={() => void usage.refetch()} />
        ) : usage.data ? (
          <>
            <QuotaMeter usage={usage.data} />

            <div className="grid gap-4 border-t pt-4 sm:grid-cols-2">
              <div className="space-y-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                    Rate limit
                  </span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        aria-label="About the rate limit"
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <Info className="size-3.5" aria-hidden="true" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      The configured per-minute ceiling. The backend does not report the current
                      rate or how much of this minute&apos;s budget remains, so no live figure is
                      shown.
                    </TooltipContent>
                  </Tooltip>
                </div>
                <p className="font-medium tabular-nums">
                  {quotaDisabled(usage.data.rate_limit_per_minute) ? (
                    <span className="text-muted-foreground font-normal">Not enforced</span>
                  ) : (
                    <>
                      {formatNumber(usage.data.rate_limit_per_minute)}
                      <span className="text-muted-foreground font-normal"> / minute</span>
                    </>
                  )}
                </p>
              </div>

              <div className="space-y-1">
                <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                  Tenant
                </span>
                <p className="truncate font-mono text-xs">{usage.data.tenant_id}</p>
              </div>
            </div>

            <p className="text-muted-foreground text-xs">
              A point-in-time snapshot. The backend keeps no historical usage series, so this panel
              shows no trend — <Badge variant="outline">requests_today</Badge> is a counter, not a
              time series.
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
