"use client";

import { Bookmark, Clock, ImageIcon, Layers, Trash2, Type, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatRelativeTime } from "@/lib/format";

import type { SearchMode } from "./search-mode";
import {
  useSearchHistory,
  type SearchFilterSnapshot,
  type SearchHistoryEntry,
} from "./search-history";

const MODE_ICONS: Record<SearchMode, LucideIcon> = {
  text: Type,
  image: ImageIcon,
  hybrid: Layers,
};

/** Short description of what a history entry actually searched for. */
function describeEntry(entry: SearchHistoryEntry): string {
  if (entry.mode === "image") return entry.imageName ?? "Image search";
  if (entry.mode === "hybrid") {
    return entry.imageName ? `${entry.query} + ${entry.imageName}` : entry.query;
  }
  return entry.query;
}

/**
 * Recent searches and saved filter sets.
 *
 * Both are local-only (the backend has no history or saved-search endpoint).
 * Replaying an entry restores its query and filters; for image and hybrid
 * entries the image itself must be re-picked, which the entry says plainly
 * rather than silently running a different search than the one listed.
 */
export function HistoryPanel({
  currentFilters,
  onReplay,
  onApplyFilters,
}: {
  currentFilters: SearchFilterSnapshot;
  onReplay: (entry: SearchHistoryEntry) => void;
  onApplyFilters: (filters: SearchFilterSnapshot) => void;
}) {
  const history = useSearchHistory((s) => s.history);
  const saved = useSearchHistory((s) => s.saved);
  const clearHistory = useSearchHistory((s) => s.clearHistory);
  const removeEntry = useSearchHistory((s) => s.removeEntry);
  const saveFilter = useSearchHistory((s) => s.saveFilter);
  const removeSavedFilter = useSearchHistory((s) => s.removeSavedFilter);

  const [filterName, setFilterName] = useState("");

  function handleSave(event: React.FormEvent) {
    event.preventDefault();
    if (!filterName.trim()) return;
    saveFilter(filterName, currentFilters);
    setFilterName("");
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock className="size-4" aria-hidden="true" />
            Recent searches
          </CardTitle>
          {history.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={clearHistory}>
              Clear
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              Searches you run appear here, with the result count and backend latency.
            </p>
          ) : (
            <ul className="space-y-1">
              {history.map((entry) => {
                const Icon = MODE_ICONS[entry.mode];
                return (
                  <li key={entry.id} className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => onReplay(entry)}
                      className="hover:bg-muted focus-visible:ring-ring flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm focus-visible:ring-2 focus-visible:outline-none"
                    >
                      <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden="true" />
                      <span className="min-w-0 flex-1 truncate">{describeEntry(entry)}</span>
                      <Badge variant="outline" className="shrink-0 tabular-nums">
                        {entry.resultCount}
                      </Badge>
                      <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                        {Math.round(entry.latencyMs)} ms
                      </span>
                      <span className="text-muted-foreground hidden shrink-0 text-xs sm:inline">
                        {formatRelativeTime(new Date(entry.at).toISOString())}
                      </span>
                    </button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove "${describeEntry(entry)}" from history`}
                      onClick={() => removeEntry(entry.id)}
                    >
                      <X className="size-3.5" />
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bookmark className="size-4" aria-hidden="true" />
            Saved filters
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <form onSubmit={handleSave} className="flex gap-2">
            <Input
              value={filterName}
              onChange={(e) => setFilterName(e.target.value)}
              placeholder="Name the current filters…"
              aria-label="Name for the current filter set"
            />
            <Button type="submit" variant="outline" disabled={!filterName.trim()}>
              Save
            </Button>
          </form>

          {saved.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              Save the brand, category, price, and result-count filters you use often.
            </p>
          ) : (
            <ul className="space-y-1">
              {saved.map((f) => (
                <li key={f.id} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onApplyFilters(f.filters)}
                    className="hover:bg-muted focus-visible:ring-ring min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-left text-sm focus-visible:ring-2 focus-visible:outline-none"
                  >
                    {f.name}
                  </button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete saved filter "${f.name}"`}
                    onClick={() => removeSavedFilter(f.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
