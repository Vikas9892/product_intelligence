import type { Metadata } from "next";

import { EnterpriseConsole } from "@/features/enterprise/enterprise-console";

export const metadata: Metadata = { title: "Enterprise" };

export default function EnterprisePage() {
  return <EnterpriseConsole />;
}
