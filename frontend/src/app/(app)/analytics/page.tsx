import { Boxes } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function AnalyticsPage() {
  return (
    <>
      <PageHeader title="Analytics" description="Usage, pipeline, and trend reporting." />
      <PagePlaceholder icon={Boxes} stage="Stage 7" />
    </>
  );
}
