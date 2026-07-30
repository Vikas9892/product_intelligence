import { BadgeDollarSign } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function PricingPage() {
  return (
    <>
      <PageHeader title="Pricing" description="Estimate a fair price from comparable products." />
      <PagePlaceholder icon={BadgeDollarSign} stage="Stage 6" />
    </>
  );
}
