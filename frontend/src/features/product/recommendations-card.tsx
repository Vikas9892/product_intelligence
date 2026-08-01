"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { useProductRecommendations } from "@/features/recommendations/queries";
import { RecommendationCard } from "@/features/recommendations/recommendation-card";

/**
 * Similar products for this item, from `GET /products/{id}/recommendations`.
 *
 * Cards are rendered by the shared `RecommendationCard`, so this view and the
 * recommendation explorer present a recommendation identically. Names are not
 * resolved here (the payload carries ids only, and the explorer is where that
 * lookup happens) — each card links out by id.
 */
export function RecommendationsCard({ id }: { id: string }) {
  const { data, isPending, isError, refetch } = useProductRecommendations(id);
  const recommendations = data?.recommendations ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommendations</CardTitle>
        <CardDescription>Similar products by hybrid similarity</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <CardSkeleton />
        ) : isError ? (
          <ErrorState title="Couldn't load recommendations" onRetry={() => void refetch()} />
        ) : recommendations.length === 0 ? (
          <EmptyState
            title="No recommendations"
            description="Recommendations are precomputed when a product is processed and cached for an hour, so a product indexed into an empty catalog has none until that expires."
          />
        ) : (
          <ul role="list" className="list-none space-y-3">
            {recommendations.map((recommendation, index) => (
              <li role="listitem" key={recommendation.product_id}>
                <RecommendationCard recommendation={recommendation} rank={index + 1} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
