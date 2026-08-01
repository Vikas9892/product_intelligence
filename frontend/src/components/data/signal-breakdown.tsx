import { ImageIcon, Tags, Type, type LucideIcon } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";

/** One named 0..1 similarity signal. */
export interface Signal {
  key: string;
  label: string;
  value: number;
  /** What the backend compares to produce this signal. */
  hint: string;
  icon: LucideIcon;
}

/**
 * The four independent similarity signals the duplicate scorer reports
 * (`DuplicateSignalBreakdown`). Labels and hints describe what each one
 * compares; the values themselves always come from the response.
 */
export const DUPLICATE_SIGNAL_META: {
  key: "image" | "text" | "metadata" | "attribute";
  label: string;
  hint: string;
  icon: LucideIcon;
}[] = [
  {
    key: "image",
    label: "Image",
    hint: "Visual similarity of the product images (CLIP embeddings).",
    icon: ImageIcon,
  },
  {
    key: "text",
    label: "Text",
    hint: "Semantic similarity of the product text (BGE embeddings).",
    icon: Type,
  },
  {
    key: "metadata",
    label: "Metadata",
    hint: "Agreement across name, brand, category, and price.",
    icon: Tags,
  },
  {
    key: "attribute",
    label: "Attribute",
    hint: "Agreement across extracted attributes such as color, material, and style.",
    icon: Tags,
  },
];

/**
 * A set of named similarity signals as labelled meters.
 *
 * Each row shows the signal's own value; no combined figure is computed here,
 * because the backend already reports its own `overall_similarity`/`confidence`
 * and re-deriving one client-side would risk contradicting it.
 */
export function SignalBreakdown({ signals, className }: { signals: Signal[]; className?: string }) {
  return (
    <ul className={cn("space-y-3", className)}>
      {signals.map((signal) => {
        const Icon = signal.icon;
        const clamped = Math.max(0, Math.min(1, signal.value));
        return (
          <li key={signal.key} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="flex items-center gap-1.5 text-sm">
                <Icon className="text-muted-foreground size-3.5" aria-hidden="true" />
                {signal.label}
              </span>
              <span className="text-sm font-medium tabular-nums">{formatScore(signal.value)}</span>
            </div>
            <Progress
              value={clamped * 100}
              aria-label={`${signal.label} similarity ${formatScore(signal.value)}`}
            />
            <p className="text-muted-foreground text-xs">{signal.hint}</p>
          </li>
        );
      })}
    </ul>
  );
}
