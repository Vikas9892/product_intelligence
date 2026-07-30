import type { Metadata } from "next";

import { ProductDetailView } from "@/features/product/product-detail-view";

export const metadata: Metadata = { title: "Product" };

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProductDetailView id={id} />;
}
