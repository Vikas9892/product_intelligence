"use client";

import { ImageIcon, Layers, Search as SearchIcon, Type } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { FileDropzone } from "@/components/forms/file-dropzone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ACCEPTED_EXTENSIONS, validateImageFile } from "@/lib/image-file";
import { cn } from "@/lib/utils";

import { modeRequirements, SEARCH_MODES, unmetRequirement, type SearchMode } from "./search-mode";

const MODE_ICONS: Record<SearchMode, LucideIcon> = {
  text: Type,
  image: ImageIcon,
  hybrid: Layers,
};

const TOP_K_OPTIONS = ["5", "10", "20", "50"];

/** The draft state the console edits. Owned by the parent workspace. */
export interface SearchDraft {
  query: string;
  file: File | null;
  topK: number;
  brand: string;
  category: string;
  minPrice: string;
  maxPrice: string;
}

/**
 * The search input surface: mode selector, query box, image picker, and
 * filters. Purely controlled — it renders the draft and reports edits; the
 * parent owns submission, so this component performs no network calls.
 */
export function SearchConsole({
  mode,
  onModeChange,
  draft,
  onDraftChange,
  onSubmit,
  isSearching,
  queryInputRef,
}: {
  mode: SearchMode;
  onModeChange: (mode: SearchMode) => void;
  draft: SearchDraft;
  onDraftChange: (patch: Partial<SearchDraft>) => void;
  onSubmit: () => void;
  isSearching: boolean;
  queryInputRef?: React.RefObject<HTMLInputElement | null>;
}) {
  const { needsQuery, needsImage } = modeRequirements(mode);
  const blocker = unmetRequirement(mode, draft);
  const activeMode = SEARCH_MODES.find((m) => m.value === mode);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (blocker || isSearching) return;
    onSubmit();
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div
        role="radiogroup"
        aria-label="Search mode"
        className="bg-muted inline-flex w-full gap-1 rounded-lg p-1 sm:w-auto"
      >
        {SEARCH_MODES.map((m) => {
          const Icon = MODE_ICONS[m.value];
          const selected = m.value === mode;
          return (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onModeChange(m.value)}
              className={cn(
                "focus-visible:ring-ring flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none sm:flex-none",
                selected
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {m.label}
            </button>
          );
        })}
      </div>

      {activeMode ? (
        <p className="text-muted-foreground text-sm" aria-live="polite">
          {activeMode.hint}
        </p>
      ) : null}

      {needsQuery ? (
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <SearchIcon
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
              aria-hidden="true"
            />
            <Input
              ref={queryInputRef}
              className="pl-9"
              placeholder="Describe the product you're looking for…"
              aria-label="Search query"
              value={draft.query}
              onChange={(e) => onDraftChange({ query: e.target.value })}
            />
          </div>
          <Button type="submit" disabled={Boolean(blocker) || isSearching} className="sm:w-32">
            {isSearching ? "Searching…" : "Search"}
          </Button>
        </div>
      ) : null}

      {needsImage ? (
        <div className="space-y-2">
          <Label>Query image</Label>
          <FileDropzone
            value={draft.file}
            onChange={(file) => onDraftChange({ file })}
            onValidate={validateImageFile}
            accept={ACCEPTED_EXTENSIONS}
            disabled={isSearching}
          />
          {!needsQuery ? (
            <Button type="submit" disabled={Boolean(blocker) || isSearching} className="w-full">
              {isSearching ? "Searching…" : "Search by image"}
            </Button>
          ) : null}
        </div>
      ) : null}

      <fieldset className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <legend className="sr-only">Filters</legend>
        <div className="space-y-1.5">
          <Label htmlFor="sf-brand">Brand</Label>
          <Input
            id="sf-brand"
            value={draft.brand}
            onChange={(e) => onDraftChange({ brand: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sf-category">Category</Label>
          <Input
            id="sf-category"
            value={draft.category}
            onChange={(e) => onDraftChange({ category: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sf-min">Min price</Label>
          <Input
            id="sf-min"
            type="number"
            min={0}
            value={draft.minPrice}
            onChange={(e) => onDraftChange({ minPrice: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sf-max">Max price</Label>
          <Input
            id="sf-max"
            type="number"
            min={0}
            value={draft.maxPrice}
            onChange={(e) => onDraftChange({ maxPrice: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sf-topk">Results</Label>
          <Select
            value={String(draft.topK)}
            onValueChange={(v) => onDraftChange({ topK: Number(v) })}
          >
            <SelectTrigger id="sf-topk">
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
      </fieldset>

      {blocker ? (
        <p className="text-muted-foreground text-sm" role="status">
          {blocker}
        </p>
      ) : null}
    </form>
  );
}
