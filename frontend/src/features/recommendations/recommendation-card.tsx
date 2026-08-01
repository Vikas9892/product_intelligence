"use client";

import { ArrowUpRight, Building2, FolderTree, Sparkles, Tag } from "lucide-react";
import Link from "next/link";

import { ConfidenceBadge } from "@/components/data/confidence-badge";
import { ScoreBar } from "@/components/data/score-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { ProductMeta } from "@/lib/api/product-metadata";
import type { RecommendationInfo } from "@/lib/api/types";
import { formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

/** How many matched tags to show before collapsing the rest into a count. */
const VISIBLE_TAGS = 6;

/**
 * One recommendation.
 *
 * Every element maps to a field on `RecommendationInfo`: `score` drives the
 * meter and the confidence level, `explanation` is the backend's own sentence,
 * and the overlap chips come from `reason` — `shared_brand`, `shared_category`,
 * `matched_attributes`, and `matched_tags`. Nothing is computed or inferred.
 *
 * `meta` is optional enrichment: the recommendations payload carries ids only,
 * so a resolved name is shown when available and the id alone when not.
 */
export function RecommendationCard({
  recommendation,
  rank,
  meta,
  className,
}: {
  recommendation: RecommendationInfo;
  rank: number;
  meta?: ProductMeta;
  className?: string;
}) {
  const { reason } = recommendation;
  const attributes = reason.matched_attributes ?? [];
  const tags = reason.matched_tags ?? [];
  const visibleTags = tags.slice(0, VISIBLE_TAGS);
  const hiddenTagCount = tags.length - visibleTags.length;

  const title = meta?.name ?? "Unresolved product";

  return (
    <Card className={className}>
      <CardContent className="space-y-3 pt-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground text-xs tabular-nums">#{rank}</span>
              <h3 className="truncate font-medium">{title}</h3>
            </div>
            <p className="text-muted-foreground truncate font-mono text-xs">
              {recommendation.product_id}
            </p>
          </div>
          <Button asChild variant="ghost" size="sm" className="shrink-0">
            <Link href={`/products/${recommendation.product_id}`} aria-label={`Open ${title}`}>
              Open
              <ArrowUpRight className="size-4" aria-hidden="true" />
            </Link>
          </Button>
        </div>

        {meta ? (
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            {meta.brand ? <span>{meta.brand}</span> : null}
            {meta.category ? <Badge variant="outline">{meta.category}</Badge> : null}
            {meta.price !== undefined ? (
              <span className="tabular-nums">{formatPrice(meta.price)}</span>
            ) : null}
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Recommendation score
          </span>
          <ConfidenceBadge score={recommendation.score} />
        </div>
        <ScoreBar value={recommendation.score} />

        <p className="flex gap-2 text-sm">
          <Sparkles className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{recommendation.explanation}</span>
        </p>

        <div className="space-y-2 border-t pt-3">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Overlap with this product
          </p>

          <div className="flex flex-wrap gap-1.5">
            <OverlapChip active={reason.shared_brand} icon={Building2} label="Same brand" />
            <OverlapChip active={reason.shared_category} icon={FolderTree} label="Same category" />
          </div>

          {attributes.length > 0 ? (
            <div className="space-y-1">
              <p className="text-muted-foreground text-xs">
                Matched attributes ({attributes.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {attributes.map((attribute) => (
                  <Badge key={attribute} variant="secondary" className="capitalize">
                    {attribute}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}

          {tags.length > 0 ? (
            <div className="space-y-1">
              <p className="text-muted-foreground text-xs">Matched tags ({tags.length})</p>
              <div className="flex flex-wrap gap-1">
                {visibleTags.map((tag) => (
                  <Badge key={tag} variant="outline" className="gap-1">
                    <Tag className="size-2.5" aria-hidden="true" />
                    {tag}
                  </Badge>
                ))}
                {hiddenTagCount > 0 ? (
                  <Badge variant="outline" className="text-muted-foreground">
                    +{hiddenTagCount} more
                  </Badge>
                ) : null}
              </div>
            </div>
          ) : null}

          {attributes.length === 0 &&
          tags.length === 0 &&
          !reason.shared_brand &&
          !reason.shared_category ? (
            <p className="text-muted-foreground text-sm">
              The backend reported no shared brand, category, attributes, or tags — this
              recommendation rests on embedding similarity alone.
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

/** A present/absent overlap signal. Absence is shown, not hidden, so the
 * reader can tell "not shared" apart from "not reported". */
function OverlapChip({
  active,
  icon: Icon,
  label,
}: {
  active: boolean;
  icon: typeof Building2;
  label: string;
}) {
  return (
    <Badge
      variant={active ? "default" : "outline"}
      className={cn(
        "gap-1",
        active
          ? "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
          : "text-muted-foreground line-through decoration-1",
      )}
    >
      <Icon className="size-3" aria-hidden="true" />
      {label}
    </Badge>
  );
}
