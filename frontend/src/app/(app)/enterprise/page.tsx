import { Building2 } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function EnterprisePage() {
  return (
    <>
      <PageHeader
        title="Enterprise"
        description="Organizations, API keys, audit log, and usage — available when the enterprise layer is enabled."
      />
      <PagePlaceholder icon={Building2} stage="Stage 7" />
    </>
  );
}
