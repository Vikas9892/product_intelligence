import {
  BadgeDollarSign,
  Boxes,
  Building2,
  CopyCheck,
  LayoutDashboard,
  type LucideIcon,
  Search,
  ServerCog,
  Sparkles,
  Upload,
} from "lucide-react";

/**
 * A single primary navigation entry.
 */
export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  /** Human-readable label used for the breadcrumb of this segment. */
  breadcrumb: string;
}

/**
 * Primary navigation.
 *
 * Every destination maps to a real backend capability (see
 * `frontend/ARCHITECTURE.md`). The pages themselves are placeholders until
 * their respective feature stages; the shell only needs to route to them.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { title: "Dashboard", href: "/", icon: LayoutDashboard, breadcrumb: "Dashboard" },
  { title: "Upload", href: "/upload", icon: Upload, breadcrumb: "Upload" },
  { title: "AI Search", href: "/search", icon: Search, breadcrumb: "AI Search" },
  { title: "Duplicates", href: "/duplicates", icon: CopyCheck, breadcrumb: "Duplicates" },
  {
    title: "Recommendations",
    href: "/recommendations",
    icon: Sparkles,
    breadcrumb: "Recommendations",
  },
  { title: "Pricing", href: "/pricing", icon: BadgeDollarSign, breadcrumb: "Pricing" },
  { title: "Analytics", href: "/analytics", icon: Boxes, breadcrumb: "Analytics" },
  { title: "Models", href: "/models", icon: Boxes, breadcrumb: "Models" },
  { title: "Enterprise", href: "/enterprise", icon: Building2, breadcrumb: "Enterprise" },
  { title: "System", href: "/system", icon: ServerCog, breadcrumb: "System" },
] as const;

/**
 * Maps a path segment to a display label for breadcrumbs. Falls back to a
 * title-cased version of the segment for anything not enumerated here.
 */
export const SEGMENT_LABELS: Record<string, string> = {
  upload: "Upload",
  search: "AI Search",
  duplicates: "Duplicates",
  recommendations: "Recommendations",
  pricing: "Pricing",
  analytics: "Analytics",
  models: "Models",
  enterprise: "Enterprise",
  system: "System",
  "api-keys": "API Keys",
  audit: "Audit",
  usage: "Usage",
};
