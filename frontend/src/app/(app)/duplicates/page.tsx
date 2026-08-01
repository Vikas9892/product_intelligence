import type { Metadata } from "next";

import { DuplicateIntelligenceView } from "@/features/duplicates/duplicate-intelligence-view";

export const metadata: Metadata = { title: "Duplicate Intelligence" };

export default function DuplicatesPage() {
  return <DuplicateIntelligenceView />;
}
