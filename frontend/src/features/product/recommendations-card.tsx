"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { useResolveProducts } from "@/features/products/use-resolve-metadata";
import { useProductRecommendations } from "@/features/recommendations/queries";
import { RecommendationCard } from "@/features/recommendations/recommendation-card";

/**
 * Similar products for this item, from `GET /products/{id}/recommendations`.
 *
 * Cards are rendered by the shared `RecommendationCard`, so this view and the
 * recommendation explorer present a recommendation identically — including
 * resolving the ids the payload carries into real products.
 *
 * That resolution was previously wired into the explorer only, so every card
 * on *this* page rendered "Unnamed product" even after the lookup endpoint
 * existed. The card-level tests passed, because they were given metadata
 * directly; nothing tested the container that had to fetch it.
 */
export function RecommendationsCard({ id }: { id: string }) {
  const { data, isPending, isError, refetch } = useProductRecommendations(id);
  const recommendations = data?.recommendations ?? [];

  const resolved = useResolveProducts(
    recommendations.map((recommendation) => recommendation.product_id),
  );
  const metaById = resolved.data?.meta ?? {};
  const missingIds = resolved.data?.missing;

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
                <RecommendationCard
                  recommendation={recommendation}
                  rank={index + 1}
                  meta={metaById[recommendation.product_id]}
                  resolutionState={
                    resolved.isPending
                      ? "loading"
                      : resolved.isError
                        ? "failed"
                        : missingIds?.has(recommendation.product_id)
                          ? "missing"
                          : "resolved"
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
