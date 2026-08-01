import { beforeEach, describe, expect, it } from "vitest";

import { useSearchHistory } from "@/features/search/search-history";

const filters = { topK: 20, brand: "", category: "", minPrice: "", maxPrice: "" };

function entry(query: string, resultCount = 3) {
  return {
    mode: "text" as const,
    query,
    imageName: null,
    filters,
    resultCount,
    latencyMs: 42,
  };
}

describe("search history store", () => {
  beforeEach(() => {
    useSearchHistory.setState({ history: [], saved: [] });
  });

  it("records searches newest-first", () => {
    const { record } = useSearchHistory.getState();
    record(entry("shoes"));
    record(entry("mugs"));

    const { history } = useSearchHistory.getState();
    expect(history.map((e) => e.query)).toEqual(["mugs", "shoes"]);
  });

  it("de-duplicates an identical repeated search instead of stacking it", () => {
    const { record } = useSearchHistory.getState();
    record(entry("shoes"));
    record(entry("mugs"));
    record(entry("shoes"));

    const { history } = useSearchHistory.getState();
    expect(history).toHaveLength(2);
    expect(history[0].query).toBe("shoes");
  });

  it("keeps a differing result count as the same search, refreshed", () => {
    const { record } = useSearchHistory.getState();
    record(entry("shoes", 3));
    record(entry("shoes", 9));

    const { history } = useSearchHistory.getState();
    expect(history).toHaveLength(1);
    expect(history[0].resultCount).toBe(9);
  });

  it("caps history at 20 entries", () => {
    const { record } = useSearchHistory.getState();
    for (let i = 0; i < 25; i += 1) record(entry(`query-${i}`));

    const { history } = useSearchHistory.getState();
    expect(history).toHaveLength(20);
    expect(history[0].query).toBe("query-24");
  });

  it("removes a single entry by id", () => {
    const { record } = useSearchHistory.getState();
    record(entry("shoes"));
    record(entry("mugs"));

    const target = useSearchHistory.getState().history[0];
    useSearchHistory.getState().removeEntry(target.id);

    expect(useSearchHistory.getState().history.map((e) => e.query)).toEqual(["shoes"]);
  });

  it("saves named filters and replaces a same-name set rather than duplicating", () => {
    const { saveFilter } = useSearchHistory.getState();
    saveFilter("Nike under 2000", { ...filters, brand: "Nike", maxPrice: "2000" });
    saveFilter("nike under 2000", { ...filters, brand: "Nike", maxPrice: "1500" });

    const { saved } = useSearchHistory.getState();
    expect(saved).toHaveLength(1);
    expect(saved[0].filters.maxPrice).toBe("1500");
  });

  it("ignores a blank filter name", () => {
    useSearchHistory.getState().saveFilter("   ", filters);
    expect(useSearchHistory.getState().saved).toHaveLength(0);
  });
});
