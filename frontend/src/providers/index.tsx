"use client";

import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

import { ThemeProvider } from "./theme-provider";

/**
 * Root client-side provider tree.
 *
 * Kept as a single composition point so `app/layout.tsx` (a server component)
 * wraps its children in exactly one client boundary. Data/query providers are
 * added here in Milestone 3; auth is added in Milestone 4.
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <TooltipProvider>{children}</TooltipProvider>
    </ThemeProvider>
  );
}
