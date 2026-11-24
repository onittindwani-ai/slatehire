/** Keep both ends of a long value (emails, paths). Never use this on numbers or dates. */
export function middleTruncate(value: string, max = 28): string {
  if (value.length <= max || max < 5) return value;
  const keep = max - 1;
  const head = Math.ceil(keep * 0.6);
  const tail = keep - head;
  return `${value.slice(0, head)}…${value.slice(value.length - tail)}`;
}

export function formatNumber(n: number, opts: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat("en-US", opts).format(n);
}

export function formatCurrency(n: number, currency = "USD"): string {
  return formatNumber(n, { style: "currency", currency, maximumFractionDigits: 0 });
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** Relative within a week, absolute after that (so old dates are never ambiguous). */
export function formatWhen(date: Date, now: Date = new Date()): string {
  const diff = now.getTime() - date.getTime();
  if (diff < 0 || diff >= 7 * DAY) {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: date.getFullYear() === now.getFullYear() ? undefined : "numeric" }).format(date);
  }
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} min ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)} h ago`;
  return `${Math.floor(diff / DAY)} d ago`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.[0] ?? "?";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/** Wait this long (ms) after opening a Sheet or Dialog before a screenshot, so it is fully opaque. */
export const OVERLAY_SETTLE_MS = 450;
