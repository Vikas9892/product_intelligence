import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";
import { ModelRegistry } from "@/features/system/model-registry";

export const metadata: Metadata = { title: "Models" };

/**
 * The model registry as its own destination.
 *
 * This route previously shipped a "coming in a later stage" placeholder while
 * the sidebar linked to it — a dead end in a finished product. It now renders
 * the same `ModelRegistry` the system page uses, so the nav entry leads
 * somewhere real without adding any new capability.
 */
export default function ModelsPage() {
  return (
    <>
      <PageHeader
        title="Models"
        description="Active and registered AI model versions, from the model registry."
      />
      <ModelRegistry />
    </>
  );
}
