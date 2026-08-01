import type { Metadata } from "next";

import { RecommendationExplorer } from "@/features/recommendations/recommendation-explorer";

export const metadata: Metadata = { title: "Recommendations" };

export default function RecommendationsPage() {
  return <RecommendationExplorer />;
}
