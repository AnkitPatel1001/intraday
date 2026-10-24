// Indian-market formatting helpers (INR, percentages, numbers).

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const inrCompactFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 2,
});

/** ₹1,23,456.78 — Indian lakh/crore grouping. */
export function formatINR(value: number | null | undefined, compact = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (!Number.isFinite(value)) return "—";
  return compact ? inrCompactFormatter.format(value) : inrFormatter.format(value);
}

/** Signed INR, e.g. +₹1,234.50 / -₹567.80 */
export function formatINRSigned(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = formatINR(Math.abs(value));
  if (value > 0) return `+${abs}`;
  if (value < 0) return `-${abs}`;
  return abs;
}

/** 12.34% */
export function formatPct(
  value: number | null | undefined,
  digits = 2,
  signed = false
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const body = `${value.toFixed(digits)}%`;
  if (signed && value > 0) return `+${body}`;
  return body;
}

/** Plain number with optional grouping/decimals. */
export function formatNumber(
  value: number | null | undefined,
  digits = 2
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Compact volume: 1.2M, 45.3K */
export function formatVolume(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value >= 1e7) return `${(value / 1e7).toFixed(2)}Cr`;
  if (value >= 1e5) return `${(value / 1e5).toFixed(2)}L`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(Math.round(value));
}

/** ISO timestamp -> "24 Oct 2026, 15:15 IST" (display only). */
export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Chart timestamps want seconds. */
export function toChartTime(iso: string): number {
  const d = new Date(iso);
  return Math.floor(d.getTime() / 1000);
}
