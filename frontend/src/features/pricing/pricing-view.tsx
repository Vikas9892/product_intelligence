"use client";

import { BadgeDollarSign } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/common/page-header";
import { DataTable, type Column } from "@/components/data/data-table";
import { ScoreBar } from "@/components/data/score-bar";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { LatencyBadge } from "@/features/search/latency-badge";
import type { ComparableProductInfo } from "@/lib/api/types";
import { formatPrice } from "@/lib/format";

import { PriceDistributionChart } from "./distribution-chart";
import { EstimateSummary, OutlierNote } from "./estimate-summary";
import { useEstimatePrice } from "./queries";

const TOP_K_OPTIONS = ["5", "10", "20", "50"];

/**
 * Pricing intelligence: a fair-price estimate with the full reasoning behind it.
 *
 * Everything comes from one `POST /pricing/estimate` response — the estimate,
 * its confidence and score, the aggregation strategy, the backend's own reason
 * sentence, and the surviving comparables (which carry their own name, brand,
 * category, price, and similarity, so no metadata lookup is needed).
 */
export function PricingView() {
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [topK, setTopK] = useState("10");

  const estimate = useEstimatePrice();
  const result = estimate.data?.data;
  const comparables = result?.comparables ?? [];

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    estimate.mutate({
      name: name.trim(),
      brand: brand.trim() || undefined,
      category: category.trim() || undefined,
      description: description.trim() || undefined,
      top_k: Number(topK),
    });
  }

  const columns: Column<ComparableProductInfo>[] = [
    {
      header: "Product",
      cell: (c) => (
        <div className="min-w-40">
          <Link href={`/products/${c.product_id}`} className="font-medium hover:underline">
            {c.name ?? "Untitled product"}
          </Link>
          <div className="text-muted-foreground font-mono text-xs">{c.product_id.slice(0, 8)}…</div>
        </div>
      ),
    },
    { header: "Brand", cell: (c) => c.brand ?? "—" },
    { header: "Category", cell: (c) => c.category ?? "—" },
    {
      header: "Price",
      cell: (c) => <span className="font-medium tabular-nums">{formatPrice(c.price)}</span>,
    },
    {
      header: "Similarity",
      cell: (c) => <ScoreBar value={c.similarity} className="min-w-24" />,
    },
  ];

  return (
    <>
      <PageHeader
        title="Pricing Intelligence"
        description="Estimate a fair price from semantically similar priced products."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Describe the product</CardTitle>
            <CardDescription>
              Retrieval uses the product text, so a name is required; the rest sharpens the match.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-1.5">
                  <Label htmlFor="p-name">Name</Label>
                  <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="p-brand">Brand</Label>
                  <Input id="p-brand" value={brand} onChange={(e) => setBrand(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="p-category">Category</Label>
                  <Input
                    id="p-category"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="p-topk">Comparables</Label>
                  <Select value={topK} onValueChange={setTopK}>
                    <SelectTrigger id="p-topk">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TOP_K_OPTIONS.map((n) => (
                        <SelectItem key={n} value={n}>
                          Top {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="p-description">Description</Label>
                <Textarea
                  id="p-description"
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <Button type="submit" disabled={!name.trim() || estimate.isPending}>
                {estimate.isPending ? "Estimating…" : "Estimate price"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {estimate.isPending ? (
          <CardSkeleton />
        ) : estimate.isError ? (
          <ErrorState
            title="Pricing failed"
            message={estimate.error instanceof Error ? estimate.error.message : undefined}
          />
        ) : !result ? (
          <EmptyState
            icon={BadgeDollarSign}
            title="No estimate yet"
            description="Describe a product above to see its estimated price, the comparables behind it, and how the number was reached."
          />
        ) : (
          <div className="space-y-6">
            {estimate.data ? (
              <LatencyBadge
                latencyMs={estimate.data.latencyMs}
                source={estimate.data.latencySource}
              />
            ) : null}

            <EstimateSummary result={result} />

            {comparables.length > 0 ? (
              <PriceDistributionChart
                comparables={comparables}
                estimatedPrice={result.estimated_price}
              />
            ) : null}

            <OutlierNote result={result} />

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Comparable products ({comparables.length})
                </CardTitle>
                <CardDescription>
                  The priced products the estimate was built from, with their similarity to the
                  described product.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DataTable
                  rows={comparables}
                  columns={columns}
                  getRowKey={(c) => c.product_id}
                  empty="The backend found no priced comparables for this description."
                />
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </>
  );
}
