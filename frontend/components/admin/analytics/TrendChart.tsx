"use client";

import { useEffect, useRef, useState } from "react";
import { useIsDark } from "@/lib/useIsDark";
import { AXIS_TEXT, GRID, ModeColor, pick } from "./colors";
import { Legend } from "./StatPrimitives";

export interface TrendSeries {
  key: string;
  label: string;
  color: ModeColor;
}

export interface TrendPoint {
  day: string; // "YYYY-MM-DD"
  values: Record<string, number>;
}

const PADDING = { top: 12, right: 12, bottom: 24, left: 36 };
const HEIGHT = 200;

function formatDayShort(day: string): string {
  const [, m, d] = day.split("-");
  return `${m}/${d}`;
}

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

export default function TrendChart({
  data,
  series,
  formatX = formatDayShort,
  formatValue = (v: number) => v.toLocaleString(),
}: {
  data: TrendPoint[];
  series: TrendSeries[];
  formatX?: (day: string) => string;
  formatValue?: (v: number) => string;
}) {
  const isDark = useIsDark();
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(w);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const n = data.length;
  const plotWidth = Math.max(width - PADDING.left - PADDING.right, 1);
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const maxValue = niceMax(Math.max(1, ...data.flatMap((d) => series.map((s) => d.values[s.key] ?? 0))));

  const xAt = (i: number) => PADDING.left + (n <= 1 ? plotWidth / 2 : (i / (n - 1)) * plotWidth);
  const yAt = (v: number) => PADDING.top + plotHeight - (v / maxValue) * plotHeight;

  function pathFor(seriesKey: string): string {
    return data.map((d, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(d.values[seriesKey] ?? 0).toFixed(1)}`).join(" ");
  }

  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || n === 0) return;
    const relX = e.clientX - rect.left - PADDING.left;
    const fraction = n <= 1 ? 0 : Math.min(Math.max(relX / plotWidth, 0), 1);
    setHoverIndex(Math.round(fraction * (n - 1)));
  }

  const gridColor = pick(GRID, isDark);
  const axisColor = pick(AXIS_TEXT, isDark);
  const gridSteps = [0, 0.25, 0.5, 0.75, 1];
  const xLabelEvery = Math.max(Math.ceil(n / 6), 1);
  const hovered = hoverIndex !== null ? data[hoverIndex] : null;

  return (
    <div>
      {series.length > 1 && (
        <div className="mb-2">
          <Legend items={series.map((s) => ({ label: s.label, color: pick(s.color, isDark) }))} />
        </div>
      )}
      <div ref={containerRef} className="relative w-full" onMouseMove={handleMove} onMouseLeave={() => setHoverIndex(null)}>
        <svg width={width} height={HEIGHT} className="overflow-visible">
          {gridSteps.map((frac) => {
            const y = PADDING.top + plotHeight * (1 - frac);
            return (
              <g key={frac}>
                <line x1={PADDING.left} x2={width - PADDING.right} y1={y} y2={y} stroke={gridColor} strokeWidth={1} />
                <text x={PADDING.left - 6} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={axisColor}>
                  {formatValue(Math.round(maxValue * frac))}
                </text>
              </g>
            );
          })}

          {data.map((d, i) =>
            i % xLabelEvery === 0 ? (
              <text key={d.day} x={xAt(i)} y={HEIGHT - 6} textAnchor="middle" fontSize={10} fill={axisColor}>
                {formatX(d.day)}
              </text>
            ) : null
          )}

          {series.map((s) => (
            <path key={s.key} d={pathFor(s.key)} fill="none" stroke={pick(s.color, isDark)} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
          ))}

          {hoverIndex !== null && (
            <>
              <line
                x1={xAt(hoverIndex)}
                x2={xAt(hoverIndex)}
                y1={PADDING.top}
                y2={PADDING.top + plotHeight}
                stroke={axisColor}
                strokeWidth={1}
                strokeDasharray="3,3"
              />
              {series.map((s) => (
                <circle
                  key={s.key}
                  cx={xAt(hoverIndex)}
                  cy={yAt(data[hoverIndex].values[s.key] ?? 0)}
                  r={4}
                  fill={pick(s.color, isDark)}
                  stroke={isDark ? "#121316" : "#ffffff"}
                  strokeWidth={1.5}
                />
              ))}
            </>
          )}
        </svg>

        {hovered && hoverIndex !== null && (
          <div
            className="pointer-events-none absolute top-0 z-10 min-w-[140px] rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-lg dark:border-white/10 dark:bg-night-surface"
            style={{
              left: Math.min(Math.max(xAt(hoverIndex) + 10, 0), width - 150),
            }}
          >
            <p className="mb-1 font-medium text-slate-700 dark:text-slate-200">{formatX(hovered.day)}</p>
            {series.map((s) => (
              <p key={s.key} className="flex items-center justify-between gap-3 text-slate-600 dark:text-slate-300">
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: pick(s.color, isDark) }} aria-hidden />
                  {s.label}
                </span>
                <span className="font-medium tabular-nums">{formatValue(hovered.values[s.key] ?? 0)}</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
