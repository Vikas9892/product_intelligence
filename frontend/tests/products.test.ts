import { describe, expect, it } from "vitest";

import { readProductMeta } from "@/lib/api/product-metadata";
import { sortResults } from "@/features/products/sorting";
import type { ProductSearchResult } from "@/lib/api/types";

function result(id: string, score: number, meta: Record<string, unknown>): ProductSearchResult {
  return { product_id: id, score, matched_modalities: ["text"], metadata: meta };
}

describe("readProductMeta", () => {
  it("coerces known fields and defaults tags to an array", () => {
    const meta = readProductMeta({
      name: "Blue Shoes",
      brand: "Nike",
      price: 1999,
      tags: ["running", "blue", 42],
      quality_score: 0.8,
    });
    expect(meta.name).toBe("Blue Shoes");
    expect(meta.brand).toBe("Nike");
    expect(meta.price).toBe(1999);
    expect(meta.tags).toEqual(["running", "blue"]);
    expect(meta.qualityScore).toBe(0.8);
  });

  it("returns undefined for missing/blank values", () => {
    const meta = readProductMeta({ name: "  ", price: "not-a-number" });
    expect(meta.name).toBeUndefined();
    expect(meta.price).toBeUndefined();
    expect(meta.tags).toEqual([]);
  });

  it("tolerates null metadata", () => {
    expect(readProductMeta(null).tags).toEqual([]);
  });
});

describe("sortResults", () => {
  const rows = [
    result("a", 0.5, { name: "Alpha", price: 30 }),
    result("b", 0.9, { name: "Bravo", price: 10 }),
    result("c", 0.7, { name: "Charlie" }), // no price
  ];

  it("sorts by relevance descending", () => {
    expect(sortResults(rows, "relevance", "desc").map((r) => r.product_id)).toEqual([
      "b",
      "c",
      "a",
    ]);
  });

  it("sorts by price ascending with missing prices last", () => {
    expect(sortResults(rows, "price", "asc").map((r) => r.product_id)).toEqual(["b", "a", "c"]);
  });

  it("sorts by name", () => {
    expect(sortResults(rows, "name", "asc").map((r) => r.product_id)).toEqual(["a", "b", "c"]);
  });
});
