import type { Metadata } from "next";

import { SearchWorkspace } from "@/features/search/search-workspace";

export const metadata: Metadata = { title: "AI Search" };

export default function SearchPage() {
  return <SearchWorkspace />;
}
