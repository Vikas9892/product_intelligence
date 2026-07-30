import type { ComponentProps, ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { cn } from "@/lib/utils";

/**
 * Card wrapper around the shadcn `ChartContainer` — the standard frame for every
 * analytics chart (title, description, themed container). Colors come from the
 * chart tokens in `globals.css` via `config`, so all charts share one palette
 * in both light and dark themes. The `children` is the Recharts chart element.
 */
export function ChartCard({
  title,
  description,
  config,
  children,
  className,
}: {
  title: string;
  description?: ReactNode;
  config: ChartConfig;
  children: ComponentProps<typeof ChartContainer>["children"];
  className?: string;
}) {
  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="aspect-video w-full">
          {children}
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
