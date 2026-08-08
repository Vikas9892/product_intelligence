"use client";

import { readProductMeta, type ProductMeta } from "@/lib/api/product-metadata";

import { EmbeddingCard } from "./embedding-card";
import { ExplainabilityCard } from "./explainability-card";
import { ImageCard } from "./image-card";
import { MetadataCard } from "./metadata-card";
import { PricingCard } from "./pricing-card";
import { ProductHeader } from "./product-header";
import { useProduct, useProductMetaCache } from "./queries";
import { RecommendationsCard } from "./recommendations-card";

/**
 * Product detail. Assembled entirely from real backend responses: descriptive
 * metadata carried from the search result, plus recommendations, pricing, and
 * explanations fetched by id. The product's own fields come from
 * `GET /products/{id}`; images are
 * not served, so those are handled honestly (see the respective cards). Each
 * section owns its loading/error state.
 */
export function ProductDetailView({ id }: { id: string }) {
  const cached = useProductMetaCache(id);
  // Authoritative fetch, with the search-seeded cache as an instant-paint
  // fallback while it resolves.
  const product = useProduct(id);
  const meta: ProductMeta | null = product.data
    ? {
        name: product.data.name ?? undefined,
        brand: product.data.brand ?? undefined,
        category: product.data.category ?? undefined,
        price: product.data.price ?? undefined,
        description: product.data.description ?? undefined,
        color: product.data.color ?? undefined,
        material: product.data.material ?? undefined,
        gender: product.data.gender ?? undefined,
        season: product.data.season ?? undefined,
        style: product.data.style ?? undefined,
        tags: product.data.tags ?? [],
        qualityScore: product.data.quality_score ?? undefined,
      }
    : cached
      ? readProductMeta(cached.metadata)
      : null;

  return (
    <>
      <ProductHeader id={id} meta={meta} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <ImageCard productId={id} alt={meta?.name ?? undefined} />
          <EmbeddingCard />
        </div>
        <div className="space-y-4 lg:col-span-2">
          <MetadataCard meta={meta} isPending={product.isPending} isError={product.isError} />
          <PricingCard id={id} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <RecommendationsCard id={id} />
        <ExplainabilityCard id={id} />
      </div>
    </>
  );
}
