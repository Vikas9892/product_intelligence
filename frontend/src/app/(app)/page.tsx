import { LayoutDashboard } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Overview of catalog activity, pipeline health, and usage."
      />
      <PagePlaceholder icon={LayoutDashboard} stage="Stage 4" />
    </>
  );
}
