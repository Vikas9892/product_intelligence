"use client";

import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

import { QueryProvider } from "./query-provider";
import { ThemeProvider } from "./theme-provider";

/**
 * Root client-side provider tree.
 *
 * Kept as a single composition point so `app/layout.tsx` (a server component)
 * wraps its children in exactly one client boundary. Query state is outermost
 * (available everywhere), then theme, then tooltip context. Auth is added in
 * Milestone 4.
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryProvider>
      <ThemeProvider>
        <TooltipProvider>{children}</TooltipProvider>
      </ThemeProvider>
    </QueryProvider>
  );
}
