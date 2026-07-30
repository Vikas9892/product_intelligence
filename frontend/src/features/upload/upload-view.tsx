"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { parseApiError } from "@/lib/api";
import { isAccepted } from "@/lib/api/endpoints/products";

import { JobProgress } from "./job-progress";
import { useJobStatus, useUploadProduct } from "./queries";
import { UploadForm } from "./upload-form";

type Phase = "idle" | "uploading" | "processing" | "failed";

/**
 * Upload orchestration: metadata form → multipart upload (with progress) →
 * async job polling → navigate to the product page on completion. Sync-mode
 * uploads (201) skip straight to navigation. All state transitions are driven
 * by real backend responses.
 */
export function UploadView() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [productId, setProductId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const cancelledRef = useRef(false);

  const upload = useUploadProduct(setUploadProgress, () => abortRef.current?.signal);
  const jobStatus = useJobStatus(phase === "processing" ? productId : null);
  const job = jobStatus.data;

  /** A completed upload changes catalog counts — refresh the dashboard's data. */
  function invalidateDashboard() {
    void queryClient.invalidateQueries({ queryKey: ["analytics"] });
  }

  useEffect(() => {
    if (phase !== "processing" || !job) return;
    if (job.status === "completed") {
      invalidateDashboard();
      toast.success("Product processed");
      router.push(`/products/${job.product_id}`);
    } else if (job.status === "failed") {
      setPhase("failed");
    }
    // invalidateDashboard is stable enough; deps kept minimal intentionally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, job, router]);

  function handleSubmit(formData: FormData) {
    setErrorMessage(null);
    setUploadProgress(0);
    cancelledRef.current = false;
    abortRef.current = new AbortController();
    setPhase("uploading");
    upload.mutate(formData, {
      onSuccess: (result) => {
        setProductId(result.product_id);
        if (isAccepted(result)) {
          setPhase("processing");
        } else {
          invalidateDashboard();
          toast.success("Product processed");
          router.push(`/products/${result.product_id}`);
        }
      },
      onError: (error) => {
        if (cancelledRef.current) return; // user-initiated cancel, not a failure
        setErrorMessage(parseApiError(error).message);
        setPhase("failed");
      },
    });
  }

  function cancelUpload() {
    cancelledRef.current = true;
    abortRef.current?.abort();
    reset();
  }

  function reset() {
    upload.reset();
    setPhase("idle");
    setProductId(null);
    setUploadProgress(0);
    setErrorMessage(null);
  }

  return (
    <>
      <PageHeader title="Upload" description="Add a product image and metadata to the catalog." />

      {phase === "idle" ? (
        <Card>
          <CardContent className="pt-6">
            <UploadForm onSubmit={handleSubmit} isSubmitting={false} />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Processing your upload</CardTitle>
            <CardDescription>
              This runs on the background worker pipeline; you&apos;ll be taken to the product when
              it finishes.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {phase === "uploading" ? (
              <div className="space-y-3">
                <p className="text-muted-foreground text-sm">Uploading image… {uploadProgress}%</p>
                <Progress value={uploadProgress} aria-label="Upload progress" />
                <Button variant="outline" size="sm" onClick={cancelUpload}>
                  Cancel
                </Button>
              </div>
            ) : null}

            {(phase === "processing" || phase === "failed") && job ? (
              <JobProgress job={job} />
            ) : null}

            {phase === "processing" && !job ? (
              <p className="text-muted-foreground text-sm">Queued — waiting for a worker…</p>
            ) : null}

            {phase === "failed" ? (
              <div className="space-y-3">
                {errorMessage ? <p className="text-destructive text-sm">{errorMessage}</p> : null}
                <Button variant="outline" onClick={reset}>
                  Upload another
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}
    </>
  );
}
