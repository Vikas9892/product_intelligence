"use client";

import { Info, Sparkles, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { CardGridSkeleton } from "@/components/feedback/loading-skeletons";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { readProductMeta } from "@/lib/api/product-metadata";
import type { ProductSearchResult } from "@/lib/api/types";
import { useSearchProducts } from "@/features/search/queries";
import { useResolveProducts } from "@/features/products/use-resolve-metadata";

import {
  DEFAULT_RECOMMENDATION_FILTERS,
  filterRecommendations,
  overlapSummary,
  sortRecommendations,
  type RecommendationFilters,
  type RecommendationSortKey,
  type SortDir,
} from "./filtering";
import { useProductRecommendations } from "./queries";
import { RecommendationCard } from "./recommendation-card";
import { RecommendationFilterBar } from "./recommendation-filters";

/** Picks the product whose recommendations are explored. */
function ProductPicker({
  onSelect,
  selected,
}: {
  onSelect: (result: ProductSearchResult) => void;
  selected: ProductSearchResult | null;
}) {
  const [query, setQuery] = useState("");
  const search = useSearchProducts();
  const results = search.data?.data.results ?? [];

  return (
    <div className="space-y-3">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim()) search.mutate({ query: query.trim(), topK: 10 });
        }}
        className="flex gap-2"
      >
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find a product to get recommendations for…"
          aria-label="Product search"
        />
        <Button type="submit" disabled={!query.trim() || search.isPending}>
          {search.isPending ? "Searching…" : "Search"}
        </Button>
      </form>

      {search.isError ? (
        <ErrorState
          title="Search failed"
          message={search.error instanceof Error ? search.error.message : undefined}
        />
      ) : results.length > 0 ? (
        <ul className="divide-y rounded-lg border" role="list" aria-label="Products">
          {results.map((result) => {
            const meta = readProductMeta(result.metadata);
            const isSelected = selected?.product_id === result.product_id;
            return (
              <li key={result.product_id} role="listitem">
                <button
                  type="button"
                  onClick={() => onSelect(result)}
                  aria-pressed={isSelected}
                  className="hover:bg-muted focus-visible:ring-ring flex w-full items-center justify-between gap-3 px-3 py-2 text-left focus-visible:ring-2 focus-visible:outline-none"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {meta.name ?? "Untitled product"}
                    </span>
                    <span className="text-muted-foreground block truncate font-mono text-xs">
                      {result.product_id}
                    </span>
                  </span>
                  {isSelected ? <Badge>Selected</Badge> : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Recommendation experience: a product's recommendations with the full reason
 * behind each one, filterable and sortable.
 *
 * Recommendations come from `GET /products/{id}/recommendations`, which returns
 * ids plus a `reason` object and the backend's own `explanation`. Product names
 * are resolved through the product lookup endpoint, since the payload
 * exists; unresolved entries say so rather than showing a blank.
 */
export function RecommendationExplorer() {
  const [selected, setSelected] = useState<ProductSearchResult | null>(null);
  const [filters, setFilters] = useState<RecommendationFilters>(DEFAULT_RECOMMENDATION_FILTERS);
  const [sortKey, setSortKey] = useState<RecommendationSortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const recommendations = useProductRecommendations(selected?.product_id ?? null);

  const items = useMemo(() => recommendations.data?.recommendations ?? [], [recommendations.data]);

  // Resolve the recommended ids to real products, in one request. This used to
  // run a text search and keep whichever ids happened to come back, which is
  // why every card rendered as "Unresolved product".
  const resolved = useResolveProducts(items.map((recommendation) => recommendation.product_id));

  const metaMap = resolved.data?.meta ?? {};
  const missingIds = resolved.data?.missing;
  const counts = useMemo(() => overlapSummary(items), [items]);
  const visible = useMemo(
    () => sortRecommendations(filterRecommendations(items, filters), sortKey, sortDir),
    [items, filters, sortKey, sortDir],
  );

  return (
    <>
      <PageHeader
        title="Recommendations"
        description="Why the platform recommends what it does, for any indexed product."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Choose a product</CardTitle>
            <CardDescription>
              Recommendations are per product, so pick one to explore.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ProductPicker onSelect={setSelected} selected={selected} />
          </CardContent>
        </Card>

        {!selected ? (
          <EmptyState
            icon={Sparkles}
            title="No product selected"
            description="Search above and pick a product to see its recommendations and the reasoning behind each one."
          />
        ) : recommendations.isPending ? (
          <CardGridSkeleton count={3} />
        ) : recommendations.isError ? (
          <ErrorState
            title="Couldn't load recommendations"
            onRetry={() => void recommendations.refetch()}
          />
        ) : items.length === 0 ? (
          <Alert>
            <TriangleAlert className="size-4" aria-hidden="true" />
            <AlertTitle>No recommendations for this product</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>
                The backend returned an empty set. Recommendations are{" "}
                <strong>precomputed by the worker when a product is processed</strong> and cached
                for an hour, so a product indexed while the catalog was empty legitimately has none
                until that cache expires — it does not mean nothing similar exists now.
              </p>
              <p className="text-muted-foreground">
                Re-checking after the cache TTL, or re-processing the product, produces a freshly
                computed set.
              </p>
            </AlertDescription>
          </Alert>
        ) : (
          <div className="space-y-4">
            <Card>
              <CardContent className="pt-6">
                <RecommendationFilterBar
                  filters={filters}
                  onFiltersChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSortKeyChange={setSortKey}
                  onSortDirToggle={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                  counts={counts}
                  total={items.length}
                />
              </CardContent>
            </Card>

            <div className="flex items-center gap-2">
              <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
                Showing {visible.length} of {items.length} recommendation
                {items.length === 1 ? "" : "s"}
              </p>
              {recommendations.data?.recommendation_type ? (
                <Badge variant="outline" className="gap-1">
                  <Info className="size-3" aria-hidden="true" />
                  {recommendations.data.recommendation_type}
                </Badge>
              ) : null}
            </div>

            {visible.length === 0 ? (
              <EmptyState
                icon={Sparkles}
                title="No recommendation matches these filters"
                description="Every returned recommendation was filtered out. Relax a filter to see them again."
              />
            ) : (
              <ul
                role="list"
                aria-label="Recommendations"
                className="grid list-none gap-4 md:grid-cols-2 xl:grid-cols-3"
              >
                {visible.map((recommendation, index) => (
                  <li role="listitem" key={recommendation.product_id}>
                    <RecommendationCard
                      recommendation={recommendation}
                      rank={index + 1}
                      meta={metaMap[recommendation.product_id]}
                      resolutionState={
                        resolved.isPending
                          ? "loading"
                          : missingIds?.has(recommendation.product_id)
                            ? "missing"
                            : "resolved"
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </>
  );
}
