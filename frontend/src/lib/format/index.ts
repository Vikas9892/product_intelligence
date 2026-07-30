/**
 * Shared value formatters, so numbers, scores, percentages, and dates read
 * consistently everywhere (one place to change locale/precision). All are pure
 * and locale-aware via `Intl`; feature views should format through these rather
 * than ad-hoc `toFixed`/`toLocaleString` calls.
 */

/** Integer/decimal grouping, e.g. 12345 → "12,345". */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(undefined, options).format(value);
}

/** A price-like number with two decimals and grouping, no currency symbol
 * (the backend does not commit to a currency), e.g. 1899.5 → "1,899.50". */
export function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/** A 0..1 ratio as a whole percent, e.g. 0.83 → "83%". */
export function formatPercent(ratio: number, fractionDigits = 0): string {
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(ratio);
}

/** A 0..1 model score to fixed precision, e.g. 0.8312 → "0.83". */
export function formatScore(score: number, fractionDigits = 2): string {
  return score.toFixed(fractionDigits);
}

/** A date (ISO string or Date) as a medium calendar date, e.g. "Jul 24, 2026". */
export function formatDate(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

/** A date-time as medium date + short time. */
export function formatDateTime(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
