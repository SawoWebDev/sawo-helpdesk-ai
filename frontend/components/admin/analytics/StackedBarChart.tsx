"use client";

import { useEffect, useRef, useState } from "react";
import { useIsDark } from "@/lib/useIsDark";
import { AXIS_TEXT, GRID, ModeColor, pick } from "./colors";
import { Legend } from "./StatPrimitives";

export interface StackKey {
  key: string;
  label: string;
  color: ModeColor;
}

export interface StackPoint {
  day: string;
  values: Record<string, number>;
  total: number;
}

const PADDING = { top: 12, right: 12, bottom: 24, left: 36 };
const HEIGHT = 200;
const SEGMENT_GAP = 2;

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

export default function StackedBarChart({ data, keys }: { data: StackPoint[]; keys: StackKey[] }) {
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
  const maxValue = niceMax(Math.max(1, ...data.map((d) => d.total)));
  const barSlot = n > 0 ? plotWidth / n : plotWidth;
  const barWidth = Math.max(Math.min(barSlot * 0.6, 28), 3);

  const yFor = (v: number) => (v / maxValue) * plotHeight;

  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || n === 0) return;
    const relX = e.clientX - rect.left - PADDING.left;
    const index = Math.min(Math.max(Math.floor(relX / barSlot), 0), n - 1);
    setHoverIndex(index);
  }

  const gridColor = pick(GRID, isDark);
  const axisColor = pick(AXIS_TEXT, isDark);
  const gridSteps = [0, 0.25, 0.5, 0.75, 1];
  const xLabelEvery = Math.max(Math.ceil(n / 6), 1);
  const hovered = hoverIndex !== null ? data[hoverIndex] : null;
  const hoverX = hoverIndex !== null ? PADDING.left + hoverIndex * barSlot + barSlot / 2 : 0;

  return (
    <div>
      <div className="mb-2">
        <Legend items={keys.map((k) => ({ label: k.label, color: pick(k.color, isDark) }))} />
      </div>
      <div ref={containerRef} className="relative w-full" onMouseMove={handleMove} onMouseLeave={() => setHoverIndex(null)}>
        <svg width={width} height={HEIGHT} className="overflow-visible">
          {gridSteps.map((frac) => {
            const y = PADDING.top + plotHeight * (1 - frac);
            return (
              <g key={frac}>
                <line x1={PADDING.left} x2={width - PADDING.right} y1={y} y2={y} stroke={gridColor} strokeWidth={1} />
                <text x={PADDING.left - 6} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={axisColor}>
                  {Math.round(maxValue * frac).toLocaleString()}
                </text>
              </g>
            );
          })}

          {data.map((d, i) =>
            i % xLabelEvery === 0 ? (
              <text key={d.day} x={PADDING.left + i * barSlot + barSlot / 2} y={HEIGHT - 6} textAnchor="middle" fontSize={10} fill={axisColor}>
                {formatDayShort(d.day)}
              </text>
            ) : null
          )}

          {data.map((d, i) => {
            const x = PADDING.left + i * barSlot + (barSlot - barWidth) / 2;
            let cursorY = PADDING.top + plotHeight;
            return (
              <g key={d.day}>
                {keys.map((k) => {
                  const raw = d.values[k.key] ?? 0;
                  if (raw <= 0) return null;
                  const h = Math.max(yFor(raw) - SEGMENT_GAP, 0);
                  cursorY -= h + SEGMENT_GAP;
                  return (
                    <rect
                      key={k.key}
                      x={x}
                      y={cursorY}
                      width={barWidth}
                      height={h}
                      rx={2}
                      fill={pick(k.color, isDark)}
                      opacity={hoverIndex === null || hoverIndex === i ? 1 : 0.45}
                    />
                  );
                })}
              </g>
            );
          })}

          {hoverIndex !== null && (
            <line
              x1={hoverX}
              x2={hoverX}
              y1={PADDING.top}
              y2={PADDING.top + plotHeight}
              stroke={axisColor}
              strokeWidth={1}
              strokeDasharray="3,3"
            />
          )}
        </svg>

        {hovered && hoverIndex !== null && (
          <div
            className="pointer-events-none absolute top-0 z-10 min-w-[150px] rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-lg dark:border-white/10 dark:bg-night-surface"
            style={{ left: Math.min(Math.max(hoverX + 10, 0), width - 160) }}
          >
            <p className="mb-1 flex items-center justify-between gap-3 font-medium text-slate-700 dark:text-slate-200">
              <span>{hovered.day}</span>
              <span className="tabular-nums">{hovered.total}</span>
            </p>
            {keys.map((k) => {
              const v = hovered.values[k.key] ?? 0;
              if (v <= 0) return null;
              return (
                <p key={k.key} className="flex items-center justify-between gap-3 text-slate-600 dark:text-slate-300">
                  <span className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: pick(k.color, isDark) }} aria-hidden />
                    {k.label}
                  </span>
                  <span className="font-medium tabular-nums">{v.toLocaleString()}</span>
                </p>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
