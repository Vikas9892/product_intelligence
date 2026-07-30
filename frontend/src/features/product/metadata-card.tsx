import { ImageOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProductMeta } from "@/lib/api/product-metadata";

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium capitalize">{value}</span>
    </div>
  );
}

/**
 * Product metadata and AI-enriched attributes, sourced from the search-result
 * payload. On direct navigation (no seeded metadata) it explains the backend's
 * lack of a get-product endpoint rather than showing blanks.
 */
export function MetadataCard({ meta }: { meta: ProductMeta | null }) {
  if (!meta) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
          <CardDescription>Product metadata</CardDescription>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          The backend exposes no get-product endpoint, so a product&apos;s own metadata is only
          available when you open it from the search results.
        </CardContent>
      </Card>
    );
  }

  const hasAttributes =
    meta.color || meta.material || meta.gender || meta.season || meta.style || meta.tags.length > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Details</CardTitle>
        <CardDescription>Metadata and AI-extracted attributes</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {meta.description ? <p className="text-sm">{meta.description}</p> : null}

        <div>
          <Field label="Color" value={meta.color} />
          <Field label="Material" value={meta.material} />
          <Field label="Gender" value={meta.gender} />
          <Field label="Season" value={meta.season} />
          <Field label="Style" value={meta.style} />
          {meta.qualityScore !== undefined ? (
            <Field label="Quality score" value={meta.qualityScore.toFixed(2)} />
          ) : null}
        </div>

        {meta.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {meta.tags.map((tag) => (
              <Badge key={tag} variant="secondary">
                {tag}
              </Badge>
            ))}
          </div>
        ) : null}

        {!hasAttributes && !meta.description ? (
          <p className="text-muted-foreground flex items-center gap-2 text-sm">
            <ImageOff className="size-4" /> No additional attributes were extracted.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
