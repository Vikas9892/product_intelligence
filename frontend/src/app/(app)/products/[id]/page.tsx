import { Boxes } from "lucide-react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export const metadata: Metadata = { title: "Product" };

/**
 * Product detail route. Reachable after an upload completes and from search
 * results. The full detail view (recommendations, pricing, explanations) is
 * built in Milestone 4; for now it confirms the route resolves.
 */
export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <PageHeader title="Product" description={`Product ${id}`} />
      <PagePlaceholder icon={Boxes} stage="Stage 4 · Milestone 4" />
    </>
  );
}
