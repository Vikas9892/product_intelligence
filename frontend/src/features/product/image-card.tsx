"use client";

import { ImageOff } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { productImageUrl } from "@/lib/api/endpoints/products";

/**
 * A product's stored image.
 *
 * The backend serves the standardized (processed) variant from
 * `GET /products/{id}/image`. It previously served nothing at all, and this
 * component rendered an apology for a capability that had never been built —
 * on a product page whose whole subject is an image the system indexed,
 * embedded, priced from and deduplicated against.
 *
 * The fallback is still honest, but it now means something specific: *this
 * product* has no stored image (it was indexed before image references were
 * recorded, or its file is gone). That is a real per-product state, not a
 * statement about the API.
 */
export function ImageCard({ productId, alt }: { productId: string; alt?: string }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <Card>
        <CardContent className="flex aspect-square flex-col items-center justify-center gap-2 p-6 text-center">
          <div className="bg-muted text-muted-foreground flex size-14 items-center justify-center rounded-full">
            <ImageOff className="size-7" />
          </div>
          <p className="text-sm font-medium">No image for this product</p>
          <p className="text-muted-foreground max-w-[15rem] text-xs">
            This product has no stored image. Products indexed before image references were recorded
            do not carry one.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="relative aspect-square p-0">
        <Image
          src={productImageUrl(productId)}
          alt={alt ?? "Product image"}
          fill
          // Same-origin through the Next proxy, so the optimizer can serve it.
          sizes="(min-width: 1024px) 33vw, 100vw"
          className="rounded-lg object-contain"
          onError={() => setFailed(true)}
        />
      </CardContent>
    </Card>
  );
}
