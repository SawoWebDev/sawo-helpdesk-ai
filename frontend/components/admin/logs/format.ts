// Formatting + color helpers for the Chat Logs / consumption UI, ported
// from sawo-chatbot's public/js/logs.js + costAnalytics.js.

export function formatCost(cost: number | null): string {
  if (cost == null) return "cost unknown";
  if (cost === 0) return "$0.00";
  return "$" + cost.toFixed(cost < 0.01 ? 4 : 2);
}

export function money4(n: number): string {
  return "$" + n.toFixed(4);
}

export function formatCompact(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(Math.round(n));
}

export function fmtMs(n: number | null | undefined): string {
  if (n == null) return "—";
  return Math.round(n).toLocaleString("en-US") + "ms";
}

export function formatDurationShort(ms: number | null): string {
  if (ms == null || ms < 0) return "—";
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return (minutes > 0 ? `${minutes}m ` : "") + `${seconds}s`;
}

// A fixed 12-color palette, assigned deterministically by a simple string
// hash so the same model always gets the same color everywhere it's badged.
const COLOR_PALETTE = [
  "#2A78D6", "#22C55E", "#C8102E", "#A855F7", "#F97316", "#0EA5E9",
  "#EAB308", "#EC4899", "#14B8A6", "#8B5CF6", "#64748B", "#92400E",
];

export function colorFor(slug: string): string {
  let hash = 0;
  for (let i = 0; i < slug.length; i++) hash = (hash * 31 + slug.charCodeAt(i)) >>> 0;
  return COLOR_PALETTE[hash % COLOR_PALETTE.length];
}

export function shortModel(id: string): string {
  const parts = id.split("/");
  return parts[parts.length - 1];
}

// Escapes regex metacharacters, then turns SQL-style % / _ wildcards into
// their regex equivalents — mirrors the server's `ILIKE '%term%'` matching
// so the client highlights exactly what the backend actually matched.
export function buildSearchRegex(term: string): RegExp | null {
  const trimmed = term.trim();
  if (!trimmed) return null;
  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = escaped.replace(/%/g, "[\\s\\S]*").replace(/_/g, "[\\s\\S]");
  try {
    return new RegExp(pattern, "gi");
  } catch {
    return null;
  }
}

export function formatDayLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function formatDisplayDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
