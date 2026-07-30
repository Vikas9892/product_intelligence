"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";

import { createQueryClient } from "@/lib/api/query-client";

/**
 * Provides the TanStack Query client to the tree. The client is created once
 * per browser session via lazy `useState` initializer (not at module scope), so
 * each mounted app gets its own client and server/client boundaries stay clean.
 */
export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
