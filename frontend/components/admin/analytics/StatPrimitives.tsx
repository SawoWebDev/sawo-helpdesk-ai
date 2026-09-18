"use client";

import { ReactNode } from "react";

export function MetricCard({
  label,
  value,
  subtitle,
  icon,
}: {
  label: string;
  value: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-night-surface">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
        {icon && <span className="text-sawo-dark dark:text-sawo-light">{icon}</span>}
      </div>
      <p className="mt-1 text-2xl font-semibold text-slate-800 dark:text-slate-100">{value}</p>
      {subtitle && <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{subtitle}</p>}
    </div>
  );
}

export function Card({
  title,
  action,
  children,
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-night-surface">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h3>
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
    <div className="flex gap-1 rounded-md border border-slate-200 p-0.5 text-xs dark:border-white/10">
      {options.map((days) => (
        <button
          key={days}
          type="button"
          onClick={() => onChange(days)}
          className={`rounded px-2 py-1 font-medium transition-colors ${
            value === days
              ? "bg-sawo text-white dark:bg-sawo-dark"
              : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/5"
          }`}
        >
          {days}d
        </button>
      ))}
    </div>
  );
}
