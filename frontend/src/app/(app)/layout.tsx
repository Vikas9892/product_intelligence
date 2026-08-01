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
      {/*
        `min-w-0` belongs on the inset itself: it is the flex sibling of the
        256px sidebar, and `SidebarInset` ships with `w-full`. Without it a
        wide descendant makes this item refuse to shrink, so the document
        scrolls sideways by exactly the sidebar width.
      */}
      <SidebarInset className="min-w-0">
        <AppTopbar />
        <OfflineIndicator />
        {/*
          A plain div, not a second <main>. shadcn's SidebarInset already
          renders the page's <main> landmark, so wrapping the content in
          another one produced two main regions — invalid, and it gives
          assistive technology two "main" landmarks to choose between. The id
          and tabIndex stay so the skip link still targets and focuses the
          content region.
        */}
        {/*
          `min-w-0` on both levels is load-bearing, not decoration. Flex items
          default to `min-width: auto`, so a wide child (a data table, a chart)
          refuses to shrink and pushes the whole page sideways instead of
          scrolling inside its own container. Measured: /models overflowed the
          document by 256px — exactly the sidebar width — at 768px until this
          was added.
        */}
        <div id="main-content" tabIndex={-1} className="min-w-0 flex-1 p-4 outline-none sm:p-6">
          <div className="mx-auto w-full max-w-6xl min-w-0 space-y-6">{children}</div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
