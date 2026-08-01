"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowDownUp, LayoutGrid, PackageSearch, Rows3, SearchX } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { CardGridSkeleton } from "@/components/feedback/loading-skeletons";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { queryKeys } from "@/lib/api";
import type { ProductSearchResult } from "@/lib/api/types";
import { SORT_OPTIONS, sortResults, type SortDir, type SortKey } from "@/features/products/sorting";
import { ResultsTable } from "@/features/products/results-table";

import { ExplainPanel } from "./explain-panel";
import { HistoryPanel } from "./history-panel";
import { LatencyBadge } from "./latency-badge";
import { useSearchProducts } from "./queries";
import { ResultCard } from "./result-card";
import { SearchConsole, type SearchDraft } from "./search-console";
import {
  useSearchHistory,
  type SearchFilterSnapshot,
  type SearchHistoryEntry,
} from "./search-history";
import { buildSearchParams, SEARCH_MODES, type SearchMode } from "./search-mode";
import { useSearchShortcuts } from "./use-search-shortcuts";

const EMPTY_DRAFT: SearchDraft = {
  query: "",
  file: null,
  topK: 20,
  brand: "",
  category: "",
  minPrice: "",
  maxPrice: "",
};

type ResultView = "grid" | "table";

function snapshotFilters(draft: SearchDraft): SearchFilterSnapshot {
  return {
    topK: draft.topK,
    brand: draft.brand,
    category: draft.category,
    minPrice: draft.minPrice,
    maxPrice: draft.maxPrice,
  };
}

/**
 * The AI search workspace — the platform's primary retrieval surface.
 *
 * Runs text, image, and hybrid search against `POST /products/search` and shows
 * exactly what came back: the fused relevance score, the matched modalities,
 * and the backend's own measured latency. Sorting and the table view reuse the
 * product-list modules rather than reimplementing them, since the backend
 * returns a single relevance-ranked page with no sort parameter.
 */
export function SearchWorkspace() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [mode, setMode] = useState<SearchMode>("text");
  const [draft, setDraft] = useState<SearchDraft>(EMPTY_DRAFT);
  const [view, setView] = useState<ResultView>("grid");
  const [sortKey, setSortKey] = useState<SortKey>("relevance");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  /** The draft as it was when the displayed results were fetched. */
  const [executed, setExecuted] = useState<{ mode: SearchMode; draft: SearchDraft } | null>(null);

  const queryInputRef = useRef<HTMLInputElement>(null);
  const record = useSearchHistory((s) => s.record);
  const search = useSearchProducts();

  const patchDraft = useCallback((patch: Partial<SearchDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
  }, []);

  const runSearch = useCallback(
    (nextMode: SearchMode, nextDraft: SearchDraft) => {
      const params = buildSearchParams(nextMode, nextDraft);
      search.mutate(params, {
        onSuccess: (response) => {
          setExecuted({ mode: nextMode, draft: nextDraft });
          record({
            mode: nextMode,
            query: nextDraft.query.trim(),
            imageName: params.file?.name ?? null,
            filters: snapshotFilters(nextDraft),
            resultCount: response.data.results.length,
            latencyMs: response.latencyMs,
          });
        },
      });
    },
    [record, search],
  );

  const handleSubmit = useCallback(() => runSearch(mode, draft), [mode, draft, runSearch]);

  const handleClear = useCallback(() => {
    setDraft(EMPTY_DRAFT);
    setExecuted(null);
    search.reset();
  }, [search]);

  const handleCycleMode = useCallback(() => {
    setMode((current) => {
      const index = SEARCH_MODES.findIndex((m) => m.value === current);
      return SEARCH_MODES[(index + 1) % SEARCH_MODES.length].value;
    });
  }, []);

  useSearchShortcuts({
    onFocusQuery: () => queryInputRef.current?.focus(),
    onClear: handleClear,
    onCycleMode: handleCycleMode,
  });

  function replayEntry(entry: SearchHistoryEntry) {
    const restored: SearchDraft = {
      ...EMPTY_DRAFT,
      ...entry.filters,
      query: entry.query,
      // The image is intentionally not restored — see `search-history.ts`.
      file: null,
    };
    setMode(entry.mode);
    setDraft(restored);
    if (entry.mode === "text") runSearch("text", restored);
  }

  function openProduct(result: ProductSearchResult) {
    // Seed the detail page from this real search result (no get-product endpoint).
    queryClient.setQueryData(queryKeys.products.meta(result.product_id), result);
    router.push(`/products/${result.product_id}`);
  }

  const results = search.data?.data.results;
  const sorted = useMemo(
    () => sortResults(results ?? [], sortKey, sortDir),
    [results, sortKey, sortDir],
  );

  return (
    <>
      <PageHeader
        title="AI Search"
        description="Text, image, and hybrid retrieval over the indexed catalog."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardContent className="pt-6">
              <SearchConsole
                mode={mode}
                onModeChange={setMode}
                draft={draft}
                onDraftChange={patchDraft}
                onSubmit={handleSubmit}
                isSearching={search.isPending}
                queryInputRef={queryInputRef}
              />
            </CardContent>
          </Card>

          {search.isPending ? (
            <CardGridSkeleton count={6} />
          ) : search.isError ? (
            <ErrorState
              title="Search failed"
              message={search.error instanceof Error ? search.error.message : undefined}
              onRetry={handleSubmit}
            />
          ) : !search.isSuccess ? (
            <EmptyState
              icon={PackageSearch}
              title="Search the catalog"
              description="Enter a description, drop in an image, or combine both. Press / to focus the query box."
            />
          ) : sorted.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title="No matching products"
              description="Nothing scored against this query. Try broader wording or clear some filters."
            />
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
                    {sorted.length} result{sorted.length === 1 ? "" : "s"}
                    {executed ? ` · ${executed.mode} search` : null}
                  </p>
                  {search.data ? (
                    <LatencyBadge
                      latencyMs={search.data.latencyMs}
                      source={search.data.latencySource}
                    />
                  ) : null}
                </div>

                <div className="flex items-center gap-2">
                  <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
                    <SelectTrigger className="w-36" aria-label="Sort by">
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
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label={view === "grid" ? "Switch to table view" : "Switch to grid view"}
                    aria-pressed={view === "table"}
                    onClick={() => setView((v) => (v === "grid" ? "table" : "grid"))}
                  >
                    {view === "grid" ? (
                      <Rows3 className="size-4" />
                    ) : (
                      <LayoutGrid className="size-4" />
                    )}
                  </Button>
                </div>
              </div>

              {view === "table" ? (
                <ResultsTable results={sorted} onOpen={openProduct} />
              ) : (
                // `role` is set explicitly on the list and its items because
                // `list-style: none` makes browsers drop the implicit list
                // semantics, which would leave assistive technology without the
                // result count or item boundaries.
                <ul
                  role="list"
                  aria-label="Search results"
                  className="grid list-none gap-4 sm:grid-cols-2 xl:grid-cols-3"
                >
                  {sorted.map((result, index) => (
                    <li role="listitem" key={result.product_id}>
                      <ResultCard
                        result={result}
                        rank={index + 1}
                        onOpen={openProduct}
                        footer={<ExplainPanel result={result} />}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <HistoryPanel
            currentFilters={snapshotFilters(draft)}
            onReplay={replayEntry}
            onApplyFilters={(filters) => patchDraft(filters)}
          />
        </aside>
      </div>
    </>
  );
}
