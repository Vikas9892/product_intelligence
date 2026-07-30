import { cn } from "@/lib/utils";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

const DOT: Record<StatusTone, string> = {
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  info: "bg-sky-500",
  neutral: "bg-muted-foreground",
};

/**
 * A small labeled status pill with a colored indicator dot — for health,
 * connection, and lifecycle states (e.g. Redis "ok", worker "degraded"). Meaning
 * is carried by the text label, never by color alone (accessibility).
 */
export function StatusChip({
  tone = "neutral",
  label,
  className,
}: {
  tone?: StatusTone;
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        className,
      )}
    >
      <span className={cn("size-2 rounded-full", DOT[tone])} aria-hidden />
      {label}
    </span>
  );
}
