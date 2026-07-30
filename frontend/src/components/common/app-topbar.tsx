import { Search } from "lucide-react";
import Link from "next/link";

import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

/**
 * Sticky top navigation bar for the app shell: sidebar toggle, breadcrumb
 * trail, a quick link to Search, and the theme switcher. Purely structural —
 * no data fetching. The Search control simply navigates to the Search page;
 * global search behavior is a later stage.
 */
export function AppTopbar() {
  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b px-4 backdrop-blur">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-5" />
      <Breadcrumbs />
      <div className="ml-auto flex items-center gap-1">
        <Button asChild variant="ghost" size="icon" aria-label="Go to search">
          <Link href="/search">
            <Search className="size-5" />
          </Link>
        </Button>
        <ThemeToggle />
      </div>
    </header>
  );
}
