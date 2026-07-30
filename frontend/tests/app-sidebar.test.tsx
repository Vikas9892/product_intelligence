import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/search" }));

import { AppSidebar } from "@/components/common/app-sidebar";
import { SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { NAV_ITEMS } from "@/config/nav";

function wrap(node: ReactNode) {
  return render(
    <TooltipProvider>
      <SidebarProvider>{node}</SidebarProvider>
    </TooltipProvider>,
  );
}

describe("AppSidebar", () => {
  it("renders a link for every primary nav item", () => {
    wrap(<AppSidebar />);
    for (const item of NAV_ITEMS) {
      const link = screen.getByRole("link", { name: new RegExp(item.title) });
      expect(link).toHaveAttribute("href", item.href);
    }
  });
});
