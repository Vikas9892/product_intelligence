import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Placeholder shown while a chart's code chunk loads.
 *
 * Charts are dynamically imported because Recharts is the largest single
 * contributor to those routes' JavaScript. This stands in for the whole card —
 * title, description, and a plot area at the same `aspect-video` ratio the real
 * `ChartCard` uses — so the surrounding layout does not shift when the chart
 * arrives.
 */
export function ChartLoading() {
  return (
    <Card>
      <CardHeader className="gap-2">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-4 w-64" />
      </CardHeader>
      <CardContent>
        <Skeleton className="aspect-video w-full" />
      </CardContent>
    </Card>
  );
}
