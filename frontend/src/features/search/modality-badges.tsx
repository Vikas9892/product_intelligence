import { HelpCircle, ImageIcon, Type } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const MODALITY_META: Record<string, { label: string; icon: LucideIcon; className: string }> = {
  image: {
    label: "Image",
    icon: ImageIcon,
    className: "border-transparent bg-info-soft text-info-foreground",
  },
  text: {
    label: "Text",
    icon: Type,
    className: "border-transparent bg-success-soft text-success-foreground",
  },
};

/**
 * The modalities the backend reports a result matched on
 * (`ProductSearchResult.matched_modalities`).
 *
 * This is the one piece of per-result retrieval provenance the search endpoint
 * actually returns, so it is rendered verbatim — an unrecognized modality
 * string is shown as-is rather than dropped, since the backend is the
 * authority on what it can emit. Meaning is carried by the icon and label, not
 * by color alone.
 */
export function ModalityBadges({
  modalities,
  className,
}: {
  modalities: string[];
  className?: string;
}) {
  if (modalities.length === 0) {
    return (
      <Badge variant="outline" className={cn("text-muted-foreground gap-1", className)}>
        <HelpCircle className="size-3" aria-hidden="true" />
        No modality reported
      </Badge>
    );
  }

  return (
    <span className={cn("flex flex-wrap gap-1", className)}>
      {modalities.map((modality) => {
        const meta = MODALITY_META[modality];
        const Icon = meta?.icon ?? HelpCircle;
        return (
          <Badge
            key={modality}
            className={cn("gap-1", meta?.className ?? "bg-muted border-transparent")}
          >
            <Icon className="size-3" aria-hidden="true" />
            {meta?.label ?? modality}
          </Badge>
        );
      })}
    </span>
  );
}
