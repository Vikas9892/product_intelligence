"use client";

import { CopyCheck } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/common/page-header";
import { SignalBreakdown, DUPLICATE_SIGNAL_META } from "@/components/data/signal-breakdown";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { CardSkeleton } from "@/components/feedback/loading-skeletons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProductMeta } from "@/lib/api/product-metadata";
import type { UploadMetadata } from "@/features/upload/upload-schema";
import { LatencyBadge } from "@/features/search/latency-badge";

import { CandidatesTable } from "./candidates-table";
import { ComparisonView } from "./comparison-view";
import { DuplicateForm } from "./duplicate-form";
import { useCandidateMetadata, useCheckDuplicate } from "./queries";
import { CrossEncoderPanel, VerdictPanel } from "./verdict-panel";

/** The submitted form values as a `ProductMeta`, for symmetric comparison. */
function submittedAsMeta(values: UploadMetadata): ProductMeta {
  return {
    name: values.name.trim() || undefined,
    brand: values.brand.trim() || undefined,
    category: values.category.trim() || undefined,
    price: values.price.trim() !== "" ? Number(values.price) : undefined,
    description: values.description.trim() || undefined,
    tags: [],
  };
}

/**
 * Duplicate intelligence: the full decision behind a duplicate verdict.
 *
 * Everything shown comes from one `POST /products/check-duplicate` response —
 * the verdict and confidence, the four independent similarity signals, the
 * cross-encoder fields (or an explicit "disabled" when the backend returns
 * null), and every candidate that was ranked. Candidate names come from one
 * supplementary `POST /products/batch` call, which resolves the ids the
 * decision returns.
 */
export function DuplicateIntelligenceView() {
  const check = useCheckDuplicate();
  // Candidate ids resolve through the batch product endpoint. This previously
  // ran a text search and kept whichever ids happened to come back.
  const candidateIds = (check.data?.data.top_candidates ?? []).map(
    (candidate) => candidate.product_id,
  );
  const candidateMeta = useCandidateMetadata(candidateIds);
  const [submitted, setSubmitted] = useState<{ values: UploadMetadata; file: File } | null>(null);

  function handleSubmit({
    formData,
    values,
    file,
  }: {
    formData: FormData;
    values: UploadMetadata;
    file: File;
  }) {
    setSubmitted({ values, file });
    check.mutate({ formData });
  }

  const result = check.data?.data;
  const metadata = candidateMeta.data?.meta ?? {};
  const matchedId = result?.matched_product ?? null;
  // `top_candidates` has a server-side default, so it is optional in the
  // generated schema; treat a missing list as an empty one.
  const candidates = result?.top_candidates ?? [];

  const signals = result?.signals
    ? DUPLICATE_SIGNAL_META.map((meta) => ({
        key: meta.key,
        label: meta.label,
        hint: meta.hint,
        icon: meta.icon,
        value: result.signals![meta.key],
      }))
    : [];

  return (
    <>
      <PageHeader
        title="Duplicate Intelligence"
        description="Check a product against the catalog and see exactly why the verdict was reached."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Product to check</CardTitle>
            <CardDescription>
              Nothing is stored or indexed — this endpoint only verifies.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DuplicateForm onSubmit={handleSubmit} isChecking={check.isPending} />
          </CardContent>
        </Card>

        {check.isPending ? (
          <CardSkeleton />
        ) : check.isError ? (
          <ErrorState
            title="Duplicate check failed"
            message={check.error instanceof Error ? check.error.message : undefined}
          />
        ) : !result ? (
          <EmptyState
            icon={CopyCheck}
            title="No check run yet"
            description="Submit a product above to see its duplicate decision, signal breakdown, and ranked candidates."
          />
        ) : (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-2">
              {check.data ? (
                <LatencyBadge latencyMs={check.data.latencyMs} source={check.data.latencySource} />
              ) : null}
            </div>

            <VerdictPanel result={result} />

            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Similarity signals</CardTitle>
                  <CardDescription>
                    The four independent signals behind the winning candidate.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {signals.length > 0 ? (
                    <SignalBreakdown signals={signals} />
                  ) : (
                    <p className="text-muted-foreground text-sm">
                      The backend reported no signals, which it does when no candidate was found at
                      all — an empty catalog, or a genuinely novel product.
                    </p>
                  )}
                </CardContent>
              </Card>

              <CrossEncoderPanel result={result} />
            </div>

            {submitted ? (
              <ComparisonView
                submitted={submittedAsMeta(submitted.values)}
                submittedFile={submitted.file}
                matchedId={matchedId}
                matchedMeta={matchedId ? (metadata[matchedId] ?? null) : null}
                metadataLookupAttempted={!candidateMeta.isPending}
              />
            ) : null}

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Ranked candidates ({candidates.length})</CardTitle>
                <CardDescription>
                  Every product the scorer evaluated, with each signal it scored.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <CandidatesTable
                  candidates={candidates}
                  matchedId={matchedId}
                  metadata={metadata}
                />
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </>
  );
}
