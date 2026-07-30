import { Search } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function SearchPage() {
  return (
    <>
      <PageHeader title="Search" description="Find similar products by image, text, or both." />
      <PagePlaceholder icon={Search} stage="Stage 5" />
    </>
  );
}
