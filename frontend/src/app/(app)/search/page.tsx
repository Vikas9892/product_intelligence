import type { Metadata } from "next";

import { ProductSearchView } from "@/features/products/product-search-view";

export const metadata: Metadata = { title: "Products" };

export default function SearchPage() {
  return <ProductSearchView />;
}
