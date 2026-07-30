import { Boxes } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function ModelsPage() {
  return (
    <>
      <PageHeader title="Models" description="Active and registered AI model versions." />
      <PagePlaceholder icon={Boxes} stage="Stage 7" />
    </>
  );
}
