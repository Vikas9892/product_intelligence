"use client";

import Link from "next/link";

import { DataTable, type Column } from "@/components/data/data-table";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { DuplicateCandidateInfo } from "@/lib/api/types";
import { formatScore } from "@/lib/format";

import type { CandidateMetaMap } from "./queries";

function ScoreCell({ value }: { value: number }) {
  return (
    <div className="min-w-24 space-y-1">
      <span className="text-xs tabular-nums">{formatScore(value)}</span>
      <Progress value={Math.max(0, Math.min(1, value)) * 100} />
    </div>
  );
}

/**
 * Every candidate the scorer evaluated, with its four independent signals and
 * the overall similarity — all straight from `top_candidates`.
 *
 * Showing the full list (not just the winner) is the point: it makes the
 * ranking auditable, so a near-miss is visible rather than hidden behind a
 * single verdict.
 */
export function CandidatesTable({
  candidates,
  matchedId,
  metadata,
}: {
  candidates: DuplicateCandidateInfo[];
  matchedId: string | null;
  metadata: CandidateMetaMap;
}) {
  const columns: Column<DuplicateCandidateInfo>[] = [
    {
      header: "Product",
      cell: (c) => {
        const meta = metadata[c.product_id];
        return (
          <div className="min-w-40">
            <Link href={`/products/${c.product_id}`} className="font-medium hover:underline">
              {meta?.name ?? "Unresolved product"}
            </Link>
            <div className="text-muted-foreground font-mono text-xs">
              {c.product_id.slice(0, 8)}…
            </div>
          </div>
        );
      },
    },
    {
      header: "",
      cell: (c) =>
        c.product_id === matchedId ? (
          <Badge className="bg-warning-soft text-warning-foreground border-transparent">
            Matched
          </Badge>
        ) : null,
    },
    { header: "Image", cell: (c) => <ScoreCell value={c.image_similarity} /> },
    { header: "Text", cell: (c) => <ScoreCell value={c.text_similarity} /> },
    { header: "Metadata", cell: (c) => <ScoreCell value={c.metadata_similarity} /> },
    { header: "Attribute", cell: (c) => <ScoreCell value={c.attribute_similarity} /> },
    {
      header: "Overall",
      cell: (c) => (
        <span className="font-medium tabular-nums">{formatScore(c.overall_similarity)}</span>
      ),
    },
  ];

  return (
    <DataTable
      rows={candidates}
      columns={columns}
      getRowKey={(c) => c.product_id}
      empty="The backend evaluated no candidates — the catalog may be empty."
    />
  );
}
