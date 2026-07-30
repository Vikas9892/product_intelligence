"use client";

import { Search } from "lucide-react";
import { useState } from "react";

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
import type { SearchParams } from "@/lib/api/endpoints/products";

const TOP_K_OPTIONS = ["10", "20", "50"];

/**
 * Search + filter bar. Query is required (the backend needs a query or image);
 * brand/category/price are real backend filters and `top_k` caps result count.
 * Emits a `SearchParams` on submit; holds only draft input state.
 */
export function SearchFilters({
  onSearch,
  isSearching,
}: {
  onSearch: (params: SearchParams) => void;
  isSearching: boolean;
}) {
  const [query, setQuery] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [topK, setTopK] = useState("20");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    onSearch({
      query: query.trim(),
      topK: Number(topK),
      brand: brand.trim() || undefined,
      category: category.trim() || undefined,
      minPrice: minPrice.trim() !== "" ? Number(minPrice) : undefined,
      maxPrice: maxPrice.trim() !== "" ? Number(maxPrice) : undefined,
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            className="pl-9"
            placeholder="Search products by description…"
            aria-label="Search query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={isSearching || !query.trim()}>
          Search
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1.5">
          <Label htmlFor="f-brand">Brand</Label>
          <Input id="f-brand" value={brand} onChange={(e) => setBrand(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="f-category">Category</Label>
          <Input id="f-category" value={category} onChange={(e) => setCategory(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="f-min">Min price</Label>
          <Input
            id="f-min"
            type="number"
            min={0}
            value={minPrice}
            onChange={(e) => setMinPrice(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="f-max">Max price</Label>
          <Input
            id="f-max"
            type="number"
            min={0}
            value={maxPrice}
            onChange={(e) => setMaxPrice(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="f-topk">Results</Label>
          <Select value={topK} onValueChange={setTopK}>
            <SelectTrigger id="f-topk">
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
      </div>
    </form>
  );
}
