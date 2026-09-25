"use client";

import { ReactNode } from "react";
import InfoTooltip from "@/components/admin/InfoTooltip";

type MetricTone = "blue" | "emerald" | "amber" | "rose" | "violet" | "brand";

const metricToneClasses: Record<MetricTone, { icon: string; wash: string; accent: string }> = {
  blue: { icon: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300", wash: "from-blue-50/90 to-white dark:from-blue-500/10 dark:to-night-surface", accent: "bg-blue-500" },
  emerald: { icon: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300", wash: "from-emerald-50/90 to-white dark:from-emerald-500/10 dark:to-night-surface", accent: "bg-emerald-500" },
  amber: { icon: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300", wash: "from-amber-50/90 to-white dark:from-amber-500/10 dark:to-night-surface", accent: "bg-amber-500" },
  rose: { icon: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300", wash: "from-rose-50/90 to-white dark:from-rose-500/10 dark:to-night-surface", accent: "bg-rose-500" },
  violet: { icon: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300", wash: "from-violet-50/90 to-white dark:from-violet-500/10 dark:to-night-surface", accent: "bg-violet-500" },
  brand: { icon: "bg-sawo-light/50 text-sawo-darker dark:bg-sawo/20 dark:text-sawo-light", wash: "from-sawo-light/30 to-white dark:from-sawo/10 dark:to-night-surface", accent: "bg-sawo" },
};

export function MetricCard({
  label,
  value,
  subtitle,
  icon,
  tone = "brand",
  hint,
}: {
  label: string;
  value: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  tone?: MetricTone;
  /** Plain-language explanation of the metric, shown in a hover/tap tooltip. */
  hint?: string;
}) {
  const classes = metricToneClasses[tone];
  return (
    <div className={`group relative overflow-hidden rounded-lg border border-slate-200 bg-gradient-to-br ${classes.wash} p-4 shadow-sm transition-shadow hover:shadow-md dark:border-white/10`}>
      <span className={`absolute inset-x-0 top-0 h-0.5 ${classes.accent}`} aria-hidden />
      <div className="flex items-start justify-between gap-2">
        <p className="flex min-w-0 items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          <span className="truncate">{label}</span>
          {hint && <InfoTooltip text={hint} label={label} />}
        </p>
        {icon && <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${classes.icon}`}>{icon}</span>}
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-800 dark:text-slate-100">{value}</p>
      {subtitle && <p className="mt-1 min-h-4 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
    </div>
  );
}

export function Card({
  title,
  action,
  children,
  hint,
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  /** Plain-language explanation of the panel, shown in a hover/tap tooltip. */
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md dark:border-white/10 dark:bg-night-surface">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex min-w-0 items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-200">
          <span className="truncate">{title}</span>
          {hint && <InfoTooltip text={hint} label={typeof title === "string" ? title : undefined} />}
        </h3>
        {action}
      </div>
      {children}
    </div>
  );
}

export interface BreakdownItem {
  key: string;
  label: string;
  value: number;
  displayValue?: string;
  color: string;
  icon?: ReactNode;
}

/** Ranked list where each row's own background is a width% bar scaled to
 * the largest value in the list — the same "CSS-div bar chart" technique
 * used for magnitude-ranked breakdowns (e.g. AICAD's BreakdownList). */
export function BreakdownList({ items, emptyLabel = "No data yet" }: { items: BreakdownItem[]; emptyLabel?: string }) {
  if (items.length === 0) {
    return <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">{emptyLabel}</p>;
  }
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((item) => (
        <li key={item.key} className="relative overflow-hidden rounded">
          <div
            className="absolute inset-y-0 left-0 rounded opacity-15"
            style={{ width: `${Math.max((item.value / max) * 100, 2)}%`, backgroundColor: item.color }}
            aria-hidden
          />
          <div className="relative flex items-center justify-between gap-3 px-2.5 py-1.5 text-sm">
            <span className="flex min-w-0 items-center gap-2 truncate text-slate-700 dark:text-slate-200">
              {item.icon ?? <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: item.color }} aria-hidden />}
              <span className="truncate">{item.label}</span>
            </span>
            <span className="shrink-0 font-medium tabular-nums text-slate-800 dark:text-slate-100">
              {item.displayValue ?? item.value.toLocaleString()}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5">
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: item.color }} aria-hidden />
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function RangeTabs({
  value,
  onChange,
  options = [7, 30, 90],
}: {
  value: number;
  onChange: (days: number) => void;
  options?: number[];
}) {
  return (
    <div className="flex gap-1 rounded-md border border-white/25 p-0.5 text-xs">
      {options.map((days) => (
        <button
          key={days}
          type="button"
          onClick={() => onChange(days)}
          className={`rounded px-2 py-1 font-medium transition-colors ${
            value === days ? "bg-white/90 text-sawo-darker" : "text-white/75 hover:bg-white/10"
          }`}
        >
          {days}d
        </button>
      ))}
    </div>
  );
}
