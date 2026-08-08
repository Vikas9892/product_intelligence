"use client";

import { ArrowUpRight } from "lucide-react";

import { ScoreBar } from "@/components/data/score-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { readProductMeta } from "@/lib/api/product-metadata";
import type { ProductSearchResult } from "@/lib/api/types";
import { formatPrice } from "@/lib/format";

import { ModalityBadges } from "./modality-badges";

/**
 * One search hit.
 *
 * Every value shown comes from the backend response: `score` is the fused
 * relevance the search endpoint returned, `matched_modalities` is its retrieval
 * provenance, and the descriptive fields come from the result's Qdrant metadata
 * payload, so no extra lookup is needed here. Nothing is derived or
 * estimated here.
 */
export function ResultCard({
  result,
  rank,
  onOpen,
  footer,
}: {
  result: ProductSearchResult;
  rank: number;
  onOpen: (result: ProductSearchResult) => void;
  /** Optional slot used by the explainability milestone. */
  footer?: React.ReactNode;
}) {
  const meta = readProductMeta(result.metadata);
  const title = meta.name ?? "Untitled product";

  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground text-xs tabular-nums">#{rank}</span>
              <h3 className="truncate font-medium">{title}</h3>
            </div>
            <p className="text-muted-foreground truncate font-mono text-xs">{result.product_id}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={() => onOpen(result)}
            aria-label={`Open ${title}`}
          >
            Open
            <ArrowUpRight className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          {meta.brand ? <span>{meta.brand}</span> : null}
          {meta.category ? <Badge variant="outline">{meta.category}</Badge> : null}
          {meta.price !== undefined ? (
            <span className="tabular-nums">{formatPrice(meta.price)}</span>
          ) : null}
        </div>

        <ModalityBadges modalities={result.matched_modalities} />

        <ScoreBar value={result.score} label="Relevance score" />

        {footer}
      </CardContent>
    </Card>
  );
}
