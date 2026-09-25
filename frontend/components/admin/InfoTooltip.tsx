"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

const BUBBLE_WIDTH = 260;
const VIEWPORT_MARGIN = 8; // keeps the bubble clear of the window edges
const GAP = 8; // space between trigger and bubble

interface Position {
  left: number;
  top: number;
  arrowLeft: number;
  placement: "top" | "bottom";
}

/**
 * Plain-language hint bubble for metric cards and panels.
 *
 * Rendered into a portal on `document.body` with `position: fixed`, because the
 * cards it sits in use `overflow-hidden` — an in-flow bubble would be clipped
 * or would stretch the card. Position is measured from the trigger on open and
 * clamped to the viewport, so the bubble never spills past an edge and flips
 * above the trigger when there isn't room below.
 */
export default function InfoTooltip({ text, label }: { text: string; label?: string }) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const bubbleRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Position | null>(null);
  // The bubble's own height, which decides whether it still fits below the
  // trigger. It is unknown until the bubble has rendered once, so it lives in
  // state and feeds back into the position calculation.
  const [height, setHeight] = useState(0);

  const measure = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();

    const maxWidth = Math.min(BUBBLE_WIDTH, window.innerWidth - VIEWPORT_MARGIN * 2);
    const triggerCenter = rect.left + rect.width / 2;
    const left = Math.min(
      Math.max(triggerCenter - maxWidth / 2, VIEWPORT_MARGIN),
      window.innerWidth - maxWidth - VIEWPORT_MARGIN
    );

    const spaceBelow = window.innerHeight - rect.bottom;
    const placement: Position["placement"] =
      height > 0 && spaceBelow < height + GAP + VIEWPORT_MARGIN && rect.top > height + GAP
        ? "top"
        : "bottom";

    setPos({
      left,
      top: placement === "bottom" ? rect.bottom + GAP : rect.top - GAP - height,
      // Arrow tracks the trigger even after the bubble is clamped sideways.
      arrowLeft: Math.min(Math.max(triggerCenter - left, 12), maxWidth - 12),
      placement,
    });
  }, [height]);

  // Measure once mounted (height is unknown until the bubble renders), then
  // keep it pinned while the page scrolls or resizes underneath it.
  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      setHeight(0);
      return;
    }
    measure();
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [open, measure]);

  // Feed the rendered height back in, so the first frame's bottom placement is
  // corrected to a top placement when there isn't actually room below.
  useLayoutEffect(() => {
    if (!open) return;
    const bubble = bubbleRef.current;
    if (!bubble) return;
    setHeight(bubble.offsetHeight);
  }, [open, pos?.left]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const maxWidth = typeof window === "undefined" ? BUBBLE_WIDTH : Math.min(BUBBLE_WIDTH, window.innerWidth - VIEWPORT_MARGIN * 2);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label ? `What does "${label}" mean?` : "What does this mean?"}
        aria-expanded={open}
        className="shrink-0 rounded-full p-0.5 text-slate-400 transition-colors hover:text-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-sawo/60 dark:text-slate-500 dark:hover:text-slate-300"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          // Cards are often wrapped in links; a tap shouldn't navigate.
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <Info size={14} aria-hidden />
      </button>

      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={bubbleRef}
            role="tooltip"
            className="pointer-events-none fixed z-[200] rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-normal leading-relaxed text-slate-600 shadow-lg dark:border-white/15 dark:bg-night-surface dark:text-slate-300"
            style={{
              width: maxWidth,
              left: pos?.left ?? 0,
              top: pos?.top ?? 0,
              // Kept laid out but invisible until both the position and the bubble's
              // own height are known, so it never flashes in the wrong spot.
              visibility: pos && height > 0 ? "visible" : "hidden",
            }}
          >
            {text}
            {pos && (
              <span
                className={`absolute h-2 w-2 rotate-45 border-slate-200 bg-white dark:border-white/15 dark:bg-night-surface ${
                  pos.placement === "bottom" ? "-top-1 border-l border-t" : "-bottom-1 border-b border-r"
                }`}
                style={{ left: pos.arrowLeft - 4 }}
                aria-hidden
              />
            )}
          </div>,
          document.body
        )}
    </>
  );
}
