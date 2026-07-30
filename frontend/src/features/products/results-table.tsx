"use client";

import { Badge } from "@/components/ui/badge";
import { DataTable, type Column } from "@/components/data/data-table";
import { ScoreBar } from "@/components/data/score-bar";
import { readProductMeta } from "@/lib/api/product-metadata";
import type { ProductSearchResult } from "@/lib/api/types";
import { formatPrice } from "@/lib/format";

/**
 * Search results as a table. Descriptive fields come from the result's Qdrant
 * metadata payload (there is no get-product endpoint). Rows open the product
 * detail page.
 */
export function ResultsTable({
  results,
  onOpen,
}: {
  results: ProductSearchResult[];
  onOpen: (result: ProductSearchResult) => void;
}) {
  const columns: Column<ProductSearchResult>[] = [
    {
      header: "Product",
      cell: (r) => {
        const meta = readProductMeta(r.metadata);
        return (
          <div className="min-w-40">
            <div className="font-medium">{meta.name ?? "Untitled product"}</div>
            <div className="text-muted-foreground font-mono text-xs">
              {r.product_id.slice(0, 8)}…
            </div>
          </div>
        );
      },
    },
    { header: "Brand", cell: (r) => readProductMeta(r.metadata).brand ?? "—" },
    { header: "Category", cell: (r) => readProductMeta(r.metadata).category ?? "—" },
    {
      header: "Price",
      className: "tabular-nums",
      cell: (r) => {
        const price = readProductMeta(r.metadata).price;
        return price !== undefined ? formatPrice(price) : "—";
      },
    },
    {
      header: "Relevance",
      cell: (r) => <ScoreBar value={r.score} className="w-28" />,
    },
    {
      header: "Match",
      cell: (r) => (
        <div className="flex flex-wrap gap-1">
          {r.matched_modalities.map((m) => (
            <Badge key={m} variant="secondary" className="capitalize">
              {m}
            </Badge>
          ))}
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={results}
      getRowKey={(r) => r.product_id}
      onRowClick={onOpen}
      rowLabel={(r) => `Open ${readProductMeta(r.metadata).name ?? r.product_id}`}
    />
  );
}
