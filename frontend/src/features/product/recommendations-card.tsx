"use client";

import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreBar } from "@/components/data/score-bar";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";

import { useRecommendations } from "./queries";

/**
 * Similar products for this item, from GET /products/{id}/recommendations.
 * Recommendation payloads carry only ids + reasons (no metadata), so each row
 * links out by id; opening it fetches what that product's endpoints allow.
 */
export function RecommendationsCard({ id }: { id: string }) {
  const router = useRouter();
  const { data, isPending, isError, refetch } = useRecommendations(id);
  const recs = data?.recommendations ?? [];

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
        ) : recs.length === 0 ? (
          <EmptyState title="No recommendations" description="Nothing similar was found." />
        ) : (
          <ul className="space-y-3">
            {recs.map((rec) => (
              <li key={rec.product_id}>
                <button
                  type="button"
                  onClick={() => router.push(`/products/${rec.product_id}`)}
                  className="hover:bg-muted/60 focus-visible:ring-ring w-full rounded-lg border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-xs">{rec.product_id.slice(0, 12)}…</span>
                    <ScoreBar value={rec.score} className="w-24" />
                  </div>
                  <p className="text-muted-foreground mt-1 text-sm">{rec.explanation}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {rec.reason.shared_brand ? <Badge variant="secondary">Same brand</Badge> : null}
                    {rec.reason.shared_category ? (
                      <Badge variant="secondary">Same category</Badge>
                    ) : null}
                    {(rec.reason.matched_tags ?? []).slice(0, 3).map((tag) => (
                      <Badge key={tag} variant="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
