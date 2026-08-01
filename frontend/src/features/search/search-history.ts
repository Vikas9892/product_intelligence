"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { SearchMode } from "./search-mode";

/** Filters that can be replayed from history. */
export interface SearchFilterSnapshot {
  topK: number;
  brand: string;
  category: string;
  minPrice: string;
  maxPrice: string;
}

/**
 * One executed search, recorded after the backend responded.
 *
 * The image `File` itself is deliberately **not** stored: it cannot be
 * serialized to localStorage, and silently replaying a stale blob would make
 * the replayed search differ from the one shown. `imageName` records that an
 * image was used so the entry is honest about what ran, and replaying an
 * image/hybrid entry restores the query and filters while prompting for the
 * image again.
 */
export interface SearchHistoryEntry {
  id: string;
  mode: SearchMode;
  query: string;
  imageName: string | null;
  filters: SearchFilterSnapshot;
  resultCount: number;
  /** Backend-measured latency in ms, as reported for that search. */
  latencyMs: number;
  /** Epoch ms. */
  at: number;
}

/** A filter set the user explicitly saved for reuse. */
export interface SavedFilter {
  id: string;
  name: string;
  filters: SearchFilterSnapshot;
}

const MAX_HISTORY = 20;

interface SearchHistoryState {
  history: SearchHistoryEntry[];
  saved: SavedFilter[];
  record: (entry: Omit<SearchHistoryEntry, "id" | "at">) => void;
  clearHistory: () => void;
  removeEntry: (id: string) => void;
  saveFilter: (name: string, filters: SearchFilterSnapshot) => void;
  removeSavedFilter: (id: string) => void;
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** True when two entries represent the same search (so we de-duplicate). */
function sameSearch(a: SearchHistoryEntry, b: Omit<SearchHistoryEntry, "id" | "at">): boolean {
  return (
    a.mode === b.mode &&
    a.query === b.query &&
    a.imageName === b.imageName &&
    a.filters.topK === b.filters.topK &&
    a.filters.brand === b.filters.brand &&
    a.filters.category === b.filters.category &&
    a.filters.minPrice === b.filters.minPrice &&
    a.filters.maxPrice === b.filters.maxPrice
  );
}

/**
 * Search history and saved filters, persisted to localStorage.
 *
 * This is genuinely client-side state: the backend exposes no search-history
 * endpoint, and inventing one is not an option. Persisting locally is the
 * honest way to offer the feature without implying server-side storage.
 */
export const useSearchHistory = create<SearchHistoryState>()(
  persist(
    (set) => ({
      history: [],
      saved: [],

      record: (entry) =>
        set((state) => {
          const deduped = state.history.filter((e) => !sameSearch(e, entry));
          const next: SearchHistoryEntry = { ...entry, id: newId(), at: Date.now() };
          return { history: [next, ...deduped].slice(0, MAX_HISTORY) };
        }),

      clearHistory: () => set({ history: [] }),

      removeEntry: (id) => set((state) => ({ history: state.history.filter((e) => e.id !== id) })),

      saveFilter: (name, filters) =>
        set((state) => {
          const trimmed = name.trim();
          if (!trimmed) return state;
          const withoutSameName = state.saved.filter(
            (f) => f.name.toLowerCase() !== trimmed.toLowerCase(),
          );
          return { saved: [{ id: newId(), name: trimmed, filters }, ...withoutSameName] };
        }),

      removeSavedFilter: (id) =>
        set((state) => ({ saved: state.saved.filter((f) => f.id !== id) })),
    }),
    { name: "pi.search.history", version: 1 },
  ),
);
