"use client";

import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { ChartCard } from "@/components/data/chart-card";
import { ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import type { TrendPoint } from "@/lib/api/endpoints/analytics";
import { formatDate, formatNumber } from "@/lib/format";

/**
 * One metric over time, so one line and no legend — the card title names the
 * measure. Text stays in ink tokens; the line colour carries no separate
 * meaning.
 */
const CHART_CONFIG = {
  value: { label: "Events", color: "var(--chart-2)" },
} satisfies ChartConfig;

/**
 * A single event metric's trend, straight from `/analytics/trends`.
 *
 * Points are plotted exactly as returned, including zeros — a quiet day is real
 * information, and dropping or interpolating it would misrepresent the series.
 */
export function TrendChart({
  title,
  description,
  points,
}: {
  title: string;
  description?: string;
  points: TrendPoint[];
}) {
  return (
    <ChartCard title={title} description={description} config={CHART_CONFIG}>
      <LineChart
        accessibilityLayer
        data={points}
        margin={{ top: 12, right: 16, left: 4, bottom: 4 }}
      >
        <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border/60" />
        <XAxis
          dataKey="period_start"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          className="text-muted-foreground"
          tickFormatter={(value: string) => formatDate(value)}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={40}
          allowDecimals={false}
          className="text-muted-foreground"
        />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(label) => formatDate(String(label))}
              formatter={(value) => (
                <span className="flex w-full justify-between gap-3">
                  <span className="text-muted-foreground">Events</span>
                  <span className="font-medium tabular-nums">{formatNumber(Number(value))}</span>
                </span>
              )}
            />
          }
        />
        {/* 2px stroke, ≥8px markers, per the shared chart conventions. */}
        <Line
          dataKey="value"
          type="monotone"
          stroke="var(--color-value)"
          strokeWidth={2}
          dot={{ r: 4 }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    </ChartCard>
  );
}
