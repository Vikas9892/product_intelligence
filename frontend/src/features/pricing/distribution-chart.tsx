"use client";

import { Bar, BarChart, CartesianGrid, LabelList, ReferenceLine, XAxis, YAxis } from "recharts";

import { ChartCard } from "@/components/data/chart-card";
import { ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import type { ComparableProductInfo } from "@/lib/api/types";
import { formatPrice, formatScore } from "@/lib/format";

import { toDistributionData } from "./spread";

/**
 * One series (price), so no legend — the card title names the measure. Text
 * stays in ink tokens; the bar colour carries no identity of its own.
 */
const CHART_CONFIG = {
  price: { label: "Price", color: "var(--chart-2)" },
} satisfies ChartConfig;

/**
 * Price distribution across the comparables the backend returned, cheapest
 * first, with the estimate drawn as a labelled reference line.
 *
 * A bar chart because the job is magnitude-by-identity over a handful of named
 * items. The estimate is a *line*, not another bar, so the two are told apart
 * by mark type rather than by colour alone. The comparables table beneath this
 * chart is its table view.
 *
 * Only prices the backend returned are plotted. Outliers were already removed
 * server-side and are absent from the response, so none can be — or are —
 * drawn here.
 */
export function PriceDistributionChart({
  comparables,
  estimatedPrice,
}: {
  comparables: ComparableProductInfo[];
  // `null` when no estimate was made: the reference line is then omitted.
  estimatedPrice: number | null;
}) {
  const data = toDistributionData(comparables);

  return (
    <ChartCard
      title="Price distribution"
      description={`${data.length} comparable${data.length === 1 ? "" : "s"} returned by the backend, cheapest first. The dashed line is the estimate.`}
      config={CHART_CONFIG}
    >
      <BarChart accessibilityLayer data={data} margin={{ top: 24, right: 12, left: 4, bottom: 4 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border/60" />
        <XAxis
          dataKey="label"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          className="text-muted-foreground"
          tickFormatter={(value: string) => (value.length > 14 ? `${value.slice(0, 13)}…` : value)}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={64}
          className="text-muted-foreground"
          tickFormatter={(value: number) => formatPrice(value)}
        />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              labelKey="label"
              formatter={(value, _name, item) => (
                <span className="flex w-full justify-between gap-3">
                  <span className="text-muted-foreground">
                    Price · similarity {formatScore(item.payload.similarity)}
                  </span>
                  <span className="font-medium tabular-nums">{formatPrice(Number(value))}</span>
                </span>
              )}
            />
          }
        />
        <ReferenceLine
          y={estimatedPrice ?? undefined}
          stroke="currentColor"
          strokeDasharray="6 4"
          strokeWidth={2}
          className="text-foreground"
          label={{
            value: estimatedPrice === null ? "" : `Estimate ${formatPrice(estimatedPrice)}`,
            position: "insideTopRight",
            className: "fill-foreground text-xs",
          }}
        />
        {/* 4px rounded data-end, anchored to the baseline; the 2px gap between
            bars comes from the surface showing through `barGap`/`barCategoryGap`. */}
        <Bar dataKey="price" fill="var(--color-price)" radius={[4, 4, 0, 0]} maxBarSize={56}>
          <LabelList
            dataKey="price"
            position="top"
            offset={8}
            className="fill-muted-foreground text-xs"
            formatter={(value) => (typeof value === "number" ? formatPrice(value) : "")}
          />
        </Bar>
      </BarChart>
    </ChartCard>
  );
}
