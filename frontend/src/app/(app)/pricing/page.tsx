import type { Metadata } from "next";

import { PricingView } from "@/features/pricing/pricing-view";

export const metadata: Metadata = { title: "Pricing Intelligence" };

export default function PricingPage() {
  return <PricingView />;
}
