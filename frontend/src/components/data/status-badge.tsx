import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * The semantic status vocabulary. Shared with `StatusChip` so a tone means the
 * same thing wherever it appears.
 */
export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

/**
 * Tone styles, expressed entirely in design tokens.
 *
 * Before this existed, nine components hand-rolled the same
 * `bg-emerald-500/15 text-emerald-700 dark:text-emerald-400` triplet, which
 * meant status colour was neither themeable nor consistent — and dark mode was
 * an ad-hoc override per site rather than a considered pair. Tokens live in
 * `globals.css` (`--success-soft` / `--success-foreground`, etc.) with
 * separately chosen light and dark values.
 */
const TONE: Record<StatusTone, string> = {
  success: "border-transparent bg-success-soft text-success-foreground",
  warning: "border-transparent bg-warning-soft text-warning-foreground",
  danger: "border-transparent bg-danger-soft text-danger-foreground",
  info: "border-transparent bg-info-soft text-info-foreground",
  neutral: "border-transparent bg-muted text-muted-foreground",
};

/**
 * A status badge.
 *
 * Meaning is always carried by the label (and optionally an icon), never by
 * colour alone — the tone is reinforcement, so the badge still reads correctly
 * in monochrome, for colour-blind users, and in forced-colours mode.
 */
export function StatusBadge({
  tone = "neutral",
  icon: Icon,
  children,
  className,
}: {
  tone?: StatusTone;
  icon?: LucideIcon;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Badge className={cn(TONE[tone], Icon ? "gap-1" : undefined, className)}>
      {Icon ? <Icon className="size-3" aria-hidden="true" /> : null}
      {children}
    </Badge>
  );
}
