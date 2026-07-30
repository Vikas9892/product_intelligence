import { CopyCheck } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function DuplicatesPage() {
  return (
    <>
      <PageHeader
        title="Duplicate Detection"
        description="Check whether a product duplicates something already in the catalog."
      />
      <PagePlaceholder icon={CopyCheck} stage="Stage 6" />
    </>
  );
}
