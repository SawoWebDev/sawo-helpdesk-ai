/**
 * Turns a source URL into a short, readable label for display under a chat
 * answer -- e.g. "https://www.sawo.com/finnish-sauna/sauna-heaters/tower-series/"
 * becomes "Tower Series". Chat answers previously showed these links as the
 * raw URL in break-all text, which reads as noise and doesn't tell a
 * non-technical user what they're actually about to open.
 *
 * This is purely cosmetic -- on any parse failure or empty result, callers
 * should fall back to the URL itself, which is still a valid (if uglier)
 * link.
 */
export function humanizeSourceUrl(url: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }

  const isPdf = parsed.pathname.toLowerCase().endsWith(".pdf");
  const segments = parsed.pathname.split("/").filter(Boolean);
  // An anchor fragment ("#SET-BASIC-H") names a specific item on a shared
  // page -- more specific than the last path segment, so it wins when
  // present.
  let raw = parsed.hash ? parsed.hash.slice(1) : segments[segments.length - 1];

  if (!raw) return isPdf ? "Manual (PDF)" : parsed.hostname.replace(/^www\./, "");

  // Manual filenames follow "Product-Name_LangCodes-Phase-Voltage.pdf" (e.g.
  // "Tower-Corner-Ni_FiEn-3P-1P.pdf") -- everything after the underscore is
  // a language/electrical spec suffix, not part of the product name, so only
  // the part before it is worth showing.
  if (isPdf) raw = raw.split("_")[0];

  const humanized = raw
    .replace(/\.pdf$/i, "")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return isPdf ? `${humanized} (Manual)` : humanized;
}
