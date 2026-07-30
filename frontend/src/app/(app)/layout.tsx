import type { ReactNode } from "react";

import { AppSidebar } from "@/components/common/app-sidebar";
import { AppTopbar } from "@/components/common/app-topbar";
import { OfflineIndicator } from "@/components/common/offline-indicator";
import { SkipLink } from "@/components/common/skip-link";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

/**
 * App-shell layout shared by every console route (route group `(app)`, which
 * does not affect the URL). Provides the collapsible sidebar, the sticky top
 * bar with breadcrumbs, and the scrollable content region. Server component —
 * the interactive pieces (sidebar state, theme toggle) are client components it
 * composes.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SidebarProvider>
      <SkipLink />
      <AppSidebar />
      <SidebarInset>
        <AppTopbar />
        <OfflineIndicator />
        <main id="main-content" tabIndex={-1} className="flex-1 p-4 outline-none sm:p-6">
          <div className="mx-auto w-full max-w-6xl space-y-6">{children}</div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
