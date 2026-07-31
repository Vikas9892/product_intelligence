import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SearchFilters } from "@/features/products/search-filters";

describe("SearchFilters", () => {
  it("submits the query with filters and default top_k", async () => {
    const onSearch = vi.fn();
    render(<SearchFilters onSearch={onSearch} isSearching={false} />);

    await userEvent.type(screen.getByLabelText("Search query"), "blue shoes");
    await userEvent.type(screen.getByLabelText("Brand"), "Nike");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(onSearch).toHaveBeenCalledWith(
      expect.objectContaining({ query: "blue shoes", brand: "Nike", topK: 20 }),
    );
  });

  it("disables search until a query is entered", async () => {
    const onSearch = vi.fn();
    render(<SearchFilters onSearch={onSearch} isSearching={false} />);

    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Search query"), "shoes");
    expect(screen.getByRole("button", { name: "Search" })).toBeEnabled();
  });
});
