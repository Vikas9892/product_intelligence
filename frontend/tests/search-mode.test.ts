import { describe, expect, it } from "vitest";

import {
  buildSearchParams,
  describeModalities,
  isModeSatisfied,
  modeRequirements,
  unmetRequirement,
} from "@/features/search/search-mode";
import { hasSearchInput } from "@/lib/api/endpoints/products";

const file = new File(["x"], "shoe.jpg", { type: "image/jpeg" });

const draft = {
  query: "blue running shoe",
  file,
  topK: 20,
  brand: "Nike",
  category: "",
  minPrice: "100",
  maxPrice: "",
};

describe("modeRequirements", () => {
  it("maps each mode to the inputs the backend needs", () => {
    expect(modeRequirements("text")).toEqual({ needsQuery: true, needsImage: false });
    expect(modeRequirements("image")).toEqual({ needsQuery: false, needsImage: true });
    expect(modeRequirements("hybrid")).toEqual({ needsQuery: true, needsImage: true });
  });
});

describe("isModeSatisfied", () => {
  it("accepts a query alone for text but not for hybrid", () => {
    const textOnly = { query: "shoes", file: null };
    expect(isModeSatisfied("text", textOnly)).toBe(true);
    expect(isModeSatisfied("hybrid", textOnly)).toBe(false);
  });

  it("accepts an image alone for image but not for text", () => {
    const imageOnly = { query: "", file };
    expect(isModeSatisfied("image", imageOnly)).toBe(true);
    expect(isModeSatisfied("text", imageOnly)).toBe(false);
  });

  it("treats a whitespace-only query as missing", () => {
    expect(isModeSatisfied("text", { query: "   ", file: null })).toBe(false);
  });
});

describe("unmetRequirement", () => {
  it("names what is missing, and returns null when ready", () => {
    expect(unmetRequirement("text", { query: "", file: null })).toBe("Enter a search query.");
    expect(unmetRequirement("image", { query: "", file: null })).toBe(
      "Choose an image to search with.",
    );
    expect(unmetRequirement("hybrid", { query: "", file: null })).toBe(
      "Enter a query and choose an image.",
    );
    expect(unmetRequirement("text", { query: "shoes", file: null })).toBeNull();
  });
});

describe("buildSearchParams", () => {
  it("sends only the inputs the chosen mode uses", () => {
    // A stale image must not leak into a text search, or the retrieval the
    // backend performs would not be the mode the user picked.
    const text = buildSearchParams("text", draft);
    expect(text.query).toBe("blue running shoe");
    expect(text.file).toBeUndefined();

    const image = buildSearchParams("image", draft);
    expect(image.file).toBe(file);
    expect(image.query).toBeUndefined();

    const hybrid = buildSearchParams("hybrid", draft);
    expect(hybrid.query).toBe("blue running shoe");
    expect(hybrid.file).toBe(file);
  });

  it("omits blank filters and coerces numeric ones", () => {
    const params = buildSearchParams("text", draft);
    expect(params.brand).toBe("Nike");
    expect(params.category).toBeUndefined();
    expect(params.minPrice).toBe(100);
    expect(params.maxPrice).toBeUndefined();
    expect(params.topK).toBe(20);
  });
});

describe("hasSearchInput", () => {
  it("requires a query or an image, matching the backend rule", () => {
    expect(hasSearchInput(null)).toBe(false);
    expect(hasSearchInput({})).toBe(false);
    expect(hasSearchInput({ query: "  " })).toBe(false);
    expect(hasSearchInput({ query: "shoes" })).toBe(true);
    expect(hasSearchInput({ file })).toBe(true);
  });
});

describe("describeModalities", () => {
  it("describes what the backend reported, including the empty case", () => {
    expect(describeModalities([])).toBe("No modality reported");
    expect(describeModalities(["text"])).toBe("Matched on text");
    expect(describeModalities(["image", "text"])).toBe("Matched on image + text");
  });
});
