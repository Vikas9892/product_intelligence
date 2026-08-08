"use client";

import { ArrowUpRight, Equal, ImageOff, Slash } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProductMeta } from "@/lib/api/product-metadata";
import { formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The fields compared side by side, in a stable, readable order. */
const COMPARED_FIELDS: { key: keyof ProductMeta; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "brand", label: "Brand" },
  { key: "category", label: "Category" },
  { key: "price", label: "Price" },
  { key: "description", label: "Description" },
  { key: "color", label: "Color" },
  { key: "material", label: "Material" },
  { key: "gender", label: "Gender" },
  { key: "style", label: "Style" },
];

type FieldVerdict = "same" | "different" | "incomparable";

function displayValue(meta: ProductMeta | null, key: keyof ProductMeta): string | null {
  if (!meta) return null;
  const value = meta[key];
  if (value === undefined || value === null || value === "") return null;
  if (key === "price" && typeof value === "number") return formatPrice(value);
  return String(value);
}

/**
 * Compares one field. Two values that are both absent are **incomparable**, not
 * "the same" — the backend simply has nothing recorded for either side, and
 * claiming a match there would overstate the evidence.
 */
function compareField(left: string | null, right: string | null): FieldVerdict {
  if (left === null || right === null) return "incomparable";
  return left.trim().toLowerCase() === right.trim().toLowerCase() ? "same" : "different";
}

function VerdictMark({ verdict }: { verdict: FieldVerdict }) {
  if (verdict === "incomparable") {
    return (
      <Badge variant="outline" className="text-muted-foreground gap-1">
        Not comparable
      </Badge>
    );
  }
  const same = verdict === "same";
  return (
    <Badge
      className={cn(
        "gap-1",
        same
          ? "bg-success-soft text-success-foreground border-transparent"
          : "bg-warning-soft text-warning-foreground border-transparent",
      )}
    >
      {same ? (
        <Equal className="size-3" aria-hidden="true" />
      ) : (
        <Slash className="size-3" aria-hidden="true" />
      )}
      {same ? "Same" : "Differs"}
    </Badge>
  );
}

function SubmittedImage({ file }: { file: File | null }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  if (!url || !file) {
    return <ImagePlaceholder label="No image submitted" />;
  }
  return (
    <Image
      src={url}
      alt={`Submitted image: ${file.name}`}
      width={480}
      height={360}
      unoptimized
      className="bg-muted max-h-56 w-full rounded-lg border object-contain"
    />
  );
}

function ImagePlaceholder({ label }: { label: string }) {
  return (
    <div className="bg-muted text-muted-foreground flex h-40 w-full flex-col items-center justify-center gap-2 rounded-lg border text-sm">
      <ImageOff className="size-6" aria-hidden="true" />
      {label}
    </div>
  );
}

/**
 * Side-by-side comparison of the submitted product against the matched one.
 *
 * The left column is fully known — it is what the user just submitted. The
 * right column is the backend's matched product, whose descriptive fields are
 * resolved through the product lookup endpoint (the decision carries ids
 * endpoint); when that lookup finds nothing, the column says so instead of
 * rendering blanks that could read as real values.
 *
 * The image comparison is deliberately asymmetric for the same reason: the
 * submitted file can be previewed locally, but the backend serves no product
 * images, so the matched side states that rather than showing a stand-in.
 */
export function ComparisonView({
  submitted,
  submittedFile,
  matchedId,
  matchedMeta,
  metadataLookupAttempted,
}: {
  submitted: ProductMeta;
  submittedFile: File | null;
  matchedId: string | null;
  matchedMeta: ProductMeta | null;
  metadataLookupAttempted: boolean;
}) {
  if (!matchedId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Comparison</CardTitle>
          <CardDescription>
            The backend reported no matching product, so there is nothing to compare against.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Side-by-side comparison</CardTitle>
        <CardDescription>
          What you submitted against the product the backend matched it to.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Submitted
            </p>
            <SubmittedImage file={submittedFile} />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Matched product
              </p>
              <Button asChild variant="ghost" size="sm">
                <Link href={`/products/${matchedId}`}>
                  Open
                  <ArrowUpRight className="size-4" aria-hidden="true" />
                </Link>
              </Button>
            </div>
            <ImagePlaceholder label="The backend serves no product images" />
            <p className="text-muted-foreground truncate font-mono text-xs">{matchedId}</p>
          </div>
        </div>

        <div>
          <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
            Metadata differences
          </p>

          {!matchedMeta ? (
            <p className="text-muted-foreground text-sm">
              {metadataLookupAttempted
                ? "The matched product could not be resolved. It may no longer be indexed. Only its id and similarity signals are available."
                : "Resolving the matched product's stored fields…"}
            </p>
          ) : (
            <ul className="divide-y">
              {COMPARED_FIELDS.map((field) => {
                const left = displayValue(submitted, field.key);
                const right = displayValue(matchedMeta, field.key);
                const verdict = compareField(left, right);
                return (
                  <li
                    key={String(field.key)}
                    className="grid gap-1 py-2 sm:grid-cols-[8rem_1fr_1fr_auto] sm:items-baseline sm:gap-3"
                  >
                    <span className="text-muted-foreground text-xs tracking-wide uppercase">
                      {field.label}
                    </span>
                    <span className="text-sm break-words">{left ?? "—"}</span>
                    <span className="text-sm break-words">{right ?? "—"}</span>
                    <VerdictMark verdict={verdict} />
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
