"use client";

import { readProductMeta } from "@/lib/api/product-metadata";

import { EmbeddingCard } from "./embedding-card";
import { ExplainabilityCard } from "./explainability-card";
import { ImageCard } from "./image-card";
import { MetadataCard } from "./metadata-card";
import { PricingCard } from "./pricing-card";
import { ProductHeader } from "./product-header";
import { useProductMetaCache } from "./queries";
import { RecommendationsCard } from "./recommendations-card";

/**
 * Product detail. Assembled entirely from real backend responses: descriptive
 * metadata carried from the search result, plus recommendations, pricing, and
 * explanations fetched by id. There is no get-product endpoint and images are
 * not served, so those are handled honestly (see the respective cards). Each
 * section owns its loading/error state.
 */
export function ProductDetailView({ id }: { id: string }) {
  const cached = useProductMetaCache(id);
  const meta = cached ? readProductMeta(cached.metadata) : null;

  return (
    <>
      <ProductHeader id={id} meta={meta} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <ImageCard />
          <EmbeddingCard />
        </div>
        <div className="space-y-4 lg:col-span-2">
          <MetadataCard meta={meta} />
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
