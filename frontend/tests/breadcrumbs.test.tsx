import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));

import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { NAV_ITEMS } from "@/config/nav";

describe("Breadcrumbs", () => {
  beforeEach(() => {
    state.pathname = "/";
  });

  it("shows Dashboard as the current page at the root", () => {
    state.pathname = "/";
    render(<Breadcrumbs />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("renders a Dashboard link plus the current section", () => {
    state.pathname = "/analytics";
    render(<Breadcrumbs />);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/");
    expect(screen.getByText("Analytics")).toBeInTheDocument();
  });

  it("maps known nested segments to friendly labels", () => {
    state.pathname = "/enterprise/api-keys";
    render(<Breadcrumbs />);
    expect(screen.getByText("Enterprise")).toBeInTheDocument();
    expect(screen.getByText("API Keys")).toBeInTheDocument();
  });
});

describe("nav config", () => {
  it("every item has a route and an icon", () => {
    for (const item of NAV_ITEMS) {
      expect(item.href.startsWith("/")).toBe(true);
      expect(item.icon).toBeTypeOf("object");
    }
  });

  it("includes the dashboard root", () => {
    expect(NAV_ITEMS.some((i) => i.href === "/")).toBe(true);
  });
});
