"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from "lucide-react";
import { formatDisplayDate } from "./format";

interface Props {
  from: string | null; // "YYYY-MM-DD"
  to: string | null;
  onChange: (from: string | null, to: string | null) => void;
}

function toDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

// A calendar date-range picker, two clicks not drag: the first click after
// no range (or a complete one) starts a fresh range; the second click
// completes it (auto-swapping if picked out of order) and immediately
// applies + closes — no separate "Apply" button. Ported from sawo-chatbot's
// logs-date-popover, minus its Asia/Manila-specific timezone handling (this
// port just uses the admin's local time consistently) and its full
// roving-tabindex arrow-key navigation (native Tab/Enter still works).
export default function DateRangePopover({ from, to, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(from ? new Date(from) : new Date()));
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  function pickDate(dateStr: string) {
    if (!from || (from && to)) {
      onChange(dateStr, null);
      return;
    }
    if (dateStr < from) {
      onChange(dateStr, from);
    } else {
      onChange(from, dateStr);
    }
    setOpen(false);
  }

  const todayStr = toDateStr(new Date());

  const days = useMemo(() => {
    const first = startOfMonth(viewMonth);
    const startWeekday = first.getDay();
    const daysInMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 0).getDate();
    const cells: (string | null)[] = [];
    for (let i = 0; i < startWeekday; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push(toDateStr(new Date(viewMonth.getFullYear(), viewMonth.getMonth(), d)));
    }
    return cells;
  }, [viewMonth]);

  const label = !from
    ? "Date range"
    : !to
      ? `${formatDisplayDate(from)} – …`
      : from === to
        ? formatDisplayDate(from)
        : `${formatDisplayDate(from)} – ${formatDisplayDate(to)}`;

  return (
    <div className="relative" ref={wrapperRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded border px-3 py-2 text-sm transition-colors ${
          from
            ? "border-sawo/50 text-sawo-darker dark:border-sawo-light/40 dark:text-sawo-light"
            : "border-slate-300 text-slate-600 dark:border-white/15 dark:text-slate-300"
        } hover:border-sawo/60 dark:hover:border-sawo-light/50`}
      >
        <CalendarIcon size={14} className="shrink-0" />
        {label}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Select a date range"
          className="absolute z-30 mt-1.5 w-72 rounded-lg border border-slate-200 bg-white p-3 shadow-xl dark:border-white/10 dark:bg-night-surface"
        >
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setViewMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
              className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/10"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
              {viewMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
            </span>
            <button
              type="button"
              onClick={() => setViewMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
              className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/10"
            >
              <ChevronRight size={16} />
            </button>
          </div>
          <div className="mb-1 grid grid-cols-7 text-center text-[10px] font-medium text-slate-400 dark:text-slate-500">
            {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
              <span key={i}>{d}</span>
            ))}
          </div>
          <div role="grid" aria-label="Days" className="grid grid-cols-7 gap-y-0.5">
            {days.map((dateStr, i) => {
              if (!dateStr) return <span key={`empty-${i}`} />;
              const isStart = dateStr === from;
              const isEnd = dateStr === to;
              const inRange = !!from && !!to && dateStr > from && dateStr < to;
              const isToday = dateStr === todayStr;
              return (
                <button
                  key={dateStr}
                  type="button"
                  onClick={() => pickDate(dateStr)}
                  className={`flex h-7 w-7 items-center justify-center text-xs transition-colors ${
                    isStart || isEnd
                      ? "bg-sawo text-white dark:bg-sawo-dark"
                      : inRange
                        ? "bg-sawo/15 text-sawo-darker dark:bg-sawo-light/15 dark:text-sawo-light"
                        : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/10"
                  } ${isStart ? "rounded-l-full" : ""} ${isEnd ? "rounded-r-full" : ""} ${
                    !isStart && !isEnd ? "rounded-full" : ""
                  } ${isToday ? "font-bold underline" : ""}`}
                >
                  {parseInt(dateStr.slice(-2), 10)}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] text-slate-400 dark:text-slate-500">Both dates are included.</p>
          <div className="mt-2 flex justify-end border-t border-slate-100 pt-2 dark:border-white/10">
            <button
              type="button"
              onClick={() => {
                onChange(null, null);
                setOpen(false);
              }}
              className="text-xs font-medium text-slate-500 hover:underline dark:text-slate-400"
            >
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
