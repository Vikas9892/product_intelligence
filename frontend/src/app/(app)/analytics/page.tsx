import type { Metadata } from "next";

import { AnalyticsView } from "@/features/analytics/analytics-view";

export const metadata: Metadata = { title: "AI Analytics" };

export default function AnalyticsPage() {
  return <AnalyticsView />;
}
