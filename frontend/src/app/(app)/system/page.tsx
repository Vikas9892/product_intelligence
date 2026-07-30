import { ServerCog } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function SystemPage() {
  return (
    <>
      <PageHeader title="System" description="Operational health and runtime statistics." />
      <PagePlaceholder icon={ServerCog} stage="Stage 7" />
    </>
  );
}
