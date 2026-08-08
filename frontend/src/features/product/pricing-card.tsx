"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge, type ConfidenceLevel } from "@/components/data/confidence-badge";
import { DataTable, type Column } from "@/components/data/data-table";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { ApiError } from "@/lib/api";
import type { ComparableProductInfo } from "@/lib/api/types";
import { formatPrice } from "@/lib/format";

import { usePricing } from "./queries";

const LEVELS: ConfidenceLevel[] = ["low", "medium", "high"];
function asLevel(value: string): ConfidenceLevel | undefined {
  return LEVELS.includes(value as ConfidenceLevel) ? (value as ConfidenceLevel) : undefined;
}

/**
 * Fair-price estimate for this product, from GET /pricing/{id}. A 404 (pricing
 * disabled, or the product isn't priceable) is shown as a soft note rather than
 * an error.
 */
export function PricingCard({ id }: { id: string }) {
  const { data, isPending, isError, error, refetch } = usePricing(id);
  const comparables = data?.comparables ?? [];

  const comparableColumns: Column<ComparableProductInfo>[] = [
    { header: "Product", cell: (c) => c.name ?? `${c.product_id.slice(0, 8)}…` },
    { header: "Brand", cell: (c) => c.brand ?? "—" },
    { header: "Price", className: "tabular-nums", cell: (c) => formatPrice(c.price) },
    { header: "Similarity", className: "tabular-nums", cell: (c) => c.similarity.toFixed(2) },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pricing</CardTitle>
        <CardDescription>Estimated from comparable products</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <CardSkeleton />
        ) : isError ? (
          error instanceof ApiError && error.isNotFound ? (
            <p className="text-muted-foreground text-sm">
              Pricing isn&apos;t available for this product.
            </p>
          ) : (
            <ErrorState title="Couldn't load pricing" onRetry={() => void refetch()} />
          )
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-baseline gap-3">
              {/*
                No-estimate renders as an em dash, never a numeral. "0.00" is a
                price: a reader sees a number and concludes the product is free
                or the estimator crashed, long before reaching the explanation
                below. Declining to estimate is not an estimate of zero.
              */}
              {data.status === "no_estimate" ? (
                <>
                  <span
                    className="text-muted-foreground text-3xl font-semibold"
                    aria-label="No price estimate"
                  >
                    —
                  </span>
                  <span className="text-sm font-medium">Not enough data</span>
                </>
              ) : (
                <>
                  <span className="text-3xl font-semibold tabular-nums">
                    {formatPrice(data.estimated_price ?? 0)}
                  </span>
                  {/*
                    The confidence chip is suppressed in the no-estimate state:
                    there is no estimate to be low-confidence about, and "Low
                    0.00" beside a dash reads as a broken number.
                  */}
                  <ConfidenceBadge level={asLevel(data.confidence)} score={data.confidence_score} />
                </>
              )}
              <span className="text-muted-foreground text-sm">
                {data.strategy} · {data.comparable_count} comparables
              </span>
            </div>
            <p className="text-muted-foreground text-sm">{data.pricing_reason}</p>
            {comparables.length > 0 ? (
              <DataTable
                columns={comparableColumns}
                rows={comparables}
                getRowKey={(c) => c.product_id}
              />
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
