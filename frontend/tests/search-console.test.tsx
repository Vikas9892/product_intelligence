import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { SearchConsole, type SearchDraft } from "@/features/search/search-console";
import type { SearchMode } from "@/features/search/search-mode";

const BASE_DRAFT: SearchDraft = {
  query: "",
  file: null,
  topK: 20,
  brand: "",
  category: "",
  minPrice: "",
  maxPrice: "",
};

/** Drives the controlled console the way the workspace does. */
function Harness({
  onSubmit = vi.fn(),
  initialMode = "text" as SearchMode,
}: {
  onSubmit?: () => void;
  initialMode?: SearchMode;
}) {
  const [mode, setMode] = useState<SearchMode>(initialMode);
  const [draft, setDraft] = useState<SearchDraft>(BASE_DRAFT);
  return (
    <SearchConsole
      mode={mode}
      onModeChange={setMode}
      draft={draft}
      onDraftChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
      onSubmit={onSubmit}
      isSearching={false}
    />
  );
}

describe("SearchConsole", () => {
  it("offers the three retrieval modes the backend supports", () => {
    render(<Harness />);
    const group = screen.getByRole("radiogroup", { name: "Search mode" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Text" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Image" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Hybrid" })).toBeInTheDocument();
  });

  it("blocks submission until the mode's inputs are supplied", async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);

    const button = screen.getByRole("button", { name: "Search" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Enter a search query.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Search query"), "blue shoes");
    expect(button).toBeEnabled();

    await userEvent.click(button);
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("swaps the query box for an image picker in image mode", async () => {
    render(<Harness />);
    expect(screen.getByLabelText("Search query")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: "Image" }));

    expect(screen.queryByLabelText("Search query")).not.toBeInTheDocument();
    expect(screen.getByText("Query image")).toBeInTheDocument();
    expect(screen.getByText("Choose an image to search with.")).toBeInTheDocument();
  });

  it("requires both inputs in hybrid mode", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("radio", { name: "Hybrid" }));

    expect(screen.getByLabelText("Search query")).toBeInTheDocument();
    expect(screen.getByText("Query image")).toBeInTheDocument();
    expect(screen.getByText("Enter a query and choose an image.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Search query"), "shoes");
    // Query alone is not enough for hybrid — the image is still outstanding.
    expect(screen.getByText("Choose an image to search with.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
  });

  it("exposes the real backend filters", () => {
    render(<Harness />);
    expect(screen.getByLabelText("Brand")).toBeInTheDocument();
    expect(screen.getByLabelText("Category")).toBeInTheDocument();
    expect(screen.getByLabelText("Min price")).toBeInTheDocument();
    expect(screen.getByLabelText("Max price")).toBeInTheDocument();
    expect(screen.getByLabelText("Results")).toBeInTheDocument();
  });
});
