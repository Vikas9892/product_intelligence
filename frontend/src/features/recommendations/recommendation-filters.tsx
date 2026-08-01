"use client";

import { ArrowDownUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  RECOMMENDATION_SORT_OPTIONS,
  type RecommendationFilters,
  type RecommendationSortKey,
  type SortDir,
} from "./filtering";

const MIN_SCORE_STEPS = [0, 0.25, 0.5, 0.75];

/**
 * Overlap filters and sorting.
 *
 * Every toggle maps to a field the backend returns, and each shows how many of
 * the fetched recommendations satisfy it — so an empty filtered set is
 * explained before it happens rather than looking like a fault.
 */
export function RecommendationFilterBar({
  filters,
  onFiltersChange,
  sortKey,
  sortDir,
  onSortKeyChange,
  onSortDirToggle,
  counts,
  total,
}: {
  filters: RecommendationFilters;
  onFiltersChange: (patch: Partial<RecommendationFilters>) => void;
  sortKey: RecommendationSortKey;
  sortDir: SortDir;
  onSortKeyChange: (key: RecommendationSortKey) => void;
  onSortDirToggle: () => void;
  counts: { sharedBrand: number; sharedCategory: number; withAttributes: number };
  total: number;
}) {
  const toggles: {
    key: keyof Pick<RecommendationFilters, "sharedBrand" | "sharedCategory" | "hasAttributes">;
    label: string;
    count: number;
  }[] = [
    { key: "sharedBrand", label: "Same brand", count: counts.sharedBrand },
    { key: "sharedCategory", label: "Same category", count: counts.sharedCategory },
    { key: "hasAttributes", label: "Has matched attributes", count: counts.withAttributes },
  ];

  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-2">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Filter by overlap
        </p>
        <div className="flex flex-wrap gap-2">
          {toggles.map((toggle) => {
            const active = filters[toggle.key];
            return (
              <button
                key={toggle.key}
                type="button"
                aria-pressed={active}
                onClick={() => onFiltersChange({ [toggle.key]: !active })}
                className={cn(
                  "focus-visible:ring-ring inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none",
                  active
                    ? "bg-primary text-primary-foreground border-transparent"
                    : "hover:bg-muted",
                )}
              >
                {toggle.label}
                <Badge
                  variant="outline"
                  className={cn(
                    "tabular-nums",
                    active && "border-primary-foreground/30 text-primary-foreground",
                  )}
                >
                  {toggle.count}/{total}
                </Badge>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="rec-min-score">Min score</Label>
          <Select
            value={String(filters.minScore)}
            onValueChange={(v) => onFiltersChange({ minScore: Number(v) })}
          >
            <SelectTrigger id="rec-min-score" className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MIN_SCORE_STEPS.map((step) => (
                <SelectItem key={step} value={String(step)}>
                  {step === 0 ? "Any" : `≥ ${formatScore(step)}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="rec-sort">Sort by</Label>
          <Select
            value={sortKey}
            onValueChange={(v) => onSortKeyChange(v as RecommendationSortKey)}
          >
            <SelectTrigger id="rec-sort" className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RECOMMENDATION_SORT_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label={`Sort ${sortDir === "asc" ? "ascending" : "descending"}`}
          onClick={onSortDirToggle}
        >
          <ArrowDownUp className="size-4" />
        </Button>
      </div>
    </div>
  );
}
