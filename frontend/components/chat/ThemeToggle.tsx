"use client";

import { MouseEvent, useEffect, useState } from "react";
import { flushSync } from "react-dom";

const REVEAL_MS = 750;
const REVEAL_EASE = [0.65, 0, 0.35, 1] as const;
const LIFT_STAGGER_MS = 80;

/** Time fraction (0-1) at which a cubic-bezier easing reaches `progress`. */
function easeTimeFor(progress: number, [x1, y1, x2, y2]: readonly number[]) {
  const bez = (s: number, a: number, b: number) => 3 * a * s * (1 - s) ** 2 + 3 * b * s * s * (1 - s) + s ** 3;
  for (let s = 0; s <= 1; s += 0.01) {
    if (bez(s, y1, y2) >= progress) return bez(s, x1, x2);
  }
  return 1;
}

/**
 * Make every [data-reveal-hit] element react the moment the growing circle's
 * edge reaches it: the delay is when the eased radius first touches the
 * element's nearest point. The value names the effect, e.g. "lift" or "glare".
 */
function triggerRevealHits(x: number, y: number, radius: number) {
  const hits = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal-hit]")).map((el) => {
    const r = el.getBoundingClientRect();
    const dx = Math.max(r.left - x, 0, x - r.right);
    const dy = Math.max(r.top - y, 0, y - r.bottom);
    return { el, r, delay: easeTimeFor(Math.min(Math.hypot(dx, dy) / radius, 1), REVEAL_EASE) * REVEAL_MS };
  });

  // Cards sit too close together for contact timing alone to separate them, so
  // they ripple one by one from top-right to bottom-left once the edge arrives.
  const lifts = hits.filter((h) => h.el.dataset.revealHit === "lift");
  if (lifts.length > 0) {
    const start = Math.min(...lifts.map((h) => h.delay));
    lifts
      .sort((a, b) => a.r.top - a.r.right - (b.r.top - b.r.right))
      .forEach((h, i) => (h.delay = start + i * LIFT_STAGGER_MS));
  }

  hits.forEach(({ el, delay }) => {
    const cls = `reveal-hit-${el.dataset.revealHit}`;
    el.classList.remove(cls);
    void el.offsetWidth; // restart the animation if a previous hit is still running
    el.style.setProperty("--hit-delay", `${Math.round(delay)}ms`);
    el.classList.add(cls);
    el.addEventListener("animationend", () => el.classList.remove(cls), { once: true });
  });
}

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setIsDark(document.documentElement.classList.contains("dark"));
    setMounted(true);
  }, []);

  function applyTheme(next: boolean) {
    setIsDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("sawo-theme", next ? "dark" : "light");
    } catch {
      // storage may be unavailable (private mode); the toggle still works for this session
    }
  }

  function toggle(e: MouseEvent<HTMLButtonElement>) {
    const next = !isDark;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Browsers without View Transitions (or users who prefer less motion) just swap instantly
    if (!document.startViewTransition || reduceMotion) {
      applyTheme(next);
      return;
    }

    // Reveal the new theme as a circle growing out of the toggle's centre
    const rect = e.currentTarget.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));

    const transition = document.startViewTransition(() => {
      flushSync(() => applyTheme(next));
    });

    transition.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: REVEAL_MS, easing: `cubic-bezier(${REVEAL_EASE.join(", ")})`, pseudoElement: "::view-transition-new(root)" },
      );
      triggerRevealHits(x, y, radius);
    });
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Light mode" : "Dark mode"}
      className="group relative h-9 w-9 shrink-0 rounded-full"
    >
      {/* The button stays put and owns the hover; only this face lifts and presses */}
      <span className="glass glass-3d glass-edge relative flex h-full w-full items-center justify-center rounded-full border border-white/30 bg-gradient-to-b from-white/30 to-white/5 text-white shadow-[inset_0_1px_1px_rgba(255,255,255,0.6),inset_0_-3px_4px_rgba(0,0,0,0.2),0_3px_6px_rgba(0,0,0,0.25)] backdrop-blur-md transition-[transform,box-shadow] duration-200 will-change-transform [backface-visibility:hidden] group-hover:shadow-[inset_0_1px_1px_rgba(255,255,255,0.7),inset_0_-3px_4px_rgba(0,0,0,0.2),0_8px_14px_-4px_rgba(0,0,0,0.35)] motion-safe:group-hover:-translate-y-0.5 motion-safe:group-active:translate-y-0 motion-safe:group-active:scale-95">
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="currentColor"
          className={`block transition-opacity duration-300 ${mounted ? "opacity-100" : "opacity-0"}`}
        >
          {isDark ? (
            <>
              <circle cx="12" cy="12" r="4.6" />
              {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
                <rect key={deg} x="11" y="1.5" width="2" height="4" rx="1" transform={`rotate(${deg} 12 12)`} />
              ))}
            </>
          ) : (
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
          )}
        </svg>
      </span>
    </button>
  );
}
