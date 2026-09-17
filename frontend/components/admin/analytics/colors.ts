// Chart palette derived from the app's brand token (tailwind.config.ts
// `sawo`) plus a small fixed categorical set, each with a light- and
// dark-mode step so fills stay legible against both chart surfaces.

export interface ModeColor {
  light: string;
  dark: string;
}

export function pick(color: ModeColor, isDark: boolean): string {
  return isDark ? color.dark : color.light;
}

// Categorical identity colors, assigned in a fixed order — never cycled or
// reassigned when a filter changes which series are present.
export const CATEGORICAL: Record<string, ModeColor> = {
  brand: { light: "#af8564", dark: "#c19a76" }, // sawo DEFAULT / light
  blue: { light: "#3b82f6", dark: "#60a5fa" },
  green: { light: "#16a34a", dark: "#4ade80" },
  violet: { light: "#8b5cf6", dark: "#a78bfa" },
};

// Status colors (state, not identity) — reserved for good/attention-needed
// pairs like answered/unanswered, never reused as a generic 4th category.
export const STATUS = {
  good: { light: "#16a34a", dark: "#4ade80" } as ModeColor,
  attention: { light: "#d97706", dark: "#fbbf24" } as ModeColor,
};

// Single-hue sequential ramp (magnitude, high -> low) built from the brand
// scale, used for ordinal bins like confidence buckets.
export const SEQUENTIAL_LIGHT = ["#8b6947", "#af8564", "#c19a76"];
export const SEQUENTIAL_DARK = ["#e4c39f", "#c19a76", "#9d745a"];

export const GRID: ModeColor = { light: "#e2e8f0", dark: "rgba(255,255,255,0.12)" };
export const AXIS_TEXT: ModeColor = { light: "#94a3b8", dark: "#64748b" };

// FAQ source values (see backend FAQEntry.source) mapped to a fixed
// categorical color + display label, reused across the FAQ Sources
// breakdown and the Content Growth chart so the same source always reads
// the same color in both places.
export const SOURCE_META: Record<string, { label: string; color: ModeColor }> = {
  manual: { label: "Manual", color: CATEGORICAL.brand },
  chat_log: { label: "Saved from Chat", color: CATEGORICAL.blue },
  chat_auto: { label: "Auto (Library)", color: CATEGORICAL.green },
  import: { label: "Import", color: CATEGORICAL.violet },
};

export function sourceLabel(source: string): string {
  return SOURCE_META[source]?.label ?? source;
}

export function sourceColor(source: string): ModeColor {
  return SOURCE_META[source]?.color ?? CATEGORICAL.brand;
}
