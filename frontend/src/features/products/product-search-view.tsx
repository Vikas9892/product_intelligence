"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowDownUp, PackageSearch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/loading-skeletons";
import { queryKeys } from "@/lib/api";
import type { SearchParams } from "@/lib/api/endpoints/products";
import type { ProductSearchResult } from "@/lib/api/types";

import { useProductSearch } from "./queries";
import { ResultsTable } from "./results-table";
import { SearchFilters } from "./search-filters";
import { SORT_OPTIONS, sortResults, type SortDir, type SortKey } from "./sorting";

const PAGE_SIZE = 10;

/**
 * Product list — search-driven, because the backend exposes no "list all"
 * endpoint. Real search + real brand/category/price filters; sorting and
 * pagination are applied client-side over the fetched result set (the backend
 * returns a single relevance-ranked page of `top_k`).
 */
export function ProductSearchView() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [params, setParams] = useState<SearchParams | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("relevance");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(1);

  const { data, isPending, isError, isFetching, refetch } = useProductSearch(params);

  const sorted = useMemo(
    () => sortResults(data?.results ?? [], sortKey, sortDir),
    [data?.results, sortKey, sortDir],
  );
  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageItems = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function handleSearch(next: SearchParams) {
    setParams(next);
    setPage(1);
  }

  function openProduct(result: ProductSearchResult) {
    // Seed the detail page's metadata from this real search result (no
    // get-product endpoint exists to fetch it on the detail page directly).
    queryClient.setQueryData(queryKeys.products.meta(result.product_id), result);
    router.push(`/products/${result.product_id}`);
  }

  return (
    <>
      <PageHeader
        title="Products"
        description="Search the catalog. The backend has no list-all endpoint, so browsing is search-driven."
      />

      <Card>
        <CardContent className="pt-6">
          <SearchFilters onSearch={handleSearch} isSearching={isFetching} />
        </CardContent>
      </Card>

      {!params ? (
        <EmptyState
          icon={PackageSearch}
          title="Search to browse the catalog"
          description="Enter a description and optional filters to find indexed products."
        />
      ) : isPending ? (
        <TableSkeleton rows={6} columns={6} />
      ) : isError ? (
        <ErrorState title="Search failed" onRetry={() => void refetch()} />
      ) : sorted.length === 0 ? (
        <EmptyState
          icon={PackageSearch}
          title="No matching products"
          description="Try a broader query or fewer filters."
        />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground text-sm">
              {sorted.length} result{sorted.length === 1 ? "" : "s"}
            </p>
            <div className="flex items-center gap-2">
              <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
                <SelectTrigger className="w-40" aria-label="Sort by">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SORT_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label={`Sort ${sortDir === "asc" ? "ascending" : "descending"}`}
                onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
              >
                <ArrowDownUp className="size-4" />
              </Button>
            </div>
          </div>

          <ResultsTable results={pageItems} onOpen={openProduct} />

          {pageCount > 1 ? (
            <div className="flex items-center justify-between gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span className="text-muted-foreground text-sm">
                Page {page} of {pageCount}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pageCount}
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              >
                Next
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </>
  );
}
