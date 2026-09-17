"use client";

import { FormEvent, useState } from "react";

export default function ChatInput({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <div className="relative z-10 w-full shrink-0 bg-[#fef9f5] dark:bg-transparent">
      <form onSubmit={handleSubmit} className="mx-auto flex w-full max-w-2xl items-center gap-2 px-4 py-3">
        {/* The rim glare lives on a sibling overlay: <input> can't host pseudo-elements */}
        <div className="relative flex-1">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Ask me anything about SAWO..."
            disabled={disabled}
            className="glass glass-input w-full rounded-full border-2 border-sawo/35 bg-white px-4 py-2.5 text-sm font-medium text-[#2a2420] shadow-[inset_0_1px_2px_rgba(0,0,0,0.06)] outline-none transition-all placeholder:font-normal placeholder:text-[#a89080] focus:border-sawo-darker focus:shadow-[inset_0_1px_2px_rgba(0,0,0,0.06),0_0_0_3px_rgba(139,105,71,0.25)] disabled:opacity-60 dark:text-slate-100"
          />
          <span aria-hidden data-reveal-hit="glare" className="glass-edge glass-edge-wide pointer-events-none absolute inset-0 rounded-full" />
        </div>
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          aria-label="Send"
          className="group relative h-10 w-10 shrink-0 rounded-full disabled:opacity-75 dark:disabled:opacity-50"
        >
          {/* The button stays put and owns the hover; only this face lifts, so the
              pointer never slips off the edge mid-lift and flickers the hover. */}
          <span data-reveal-hit="lift" className="glass glass-3d glass-edge relative flex h-full w-full items-center justify-center rounded-full border border-transparent bg-gradient-to-br from-sawo-dark to-sawo-darker text-white shadow-[inset_0_2px_2px_rgba(255,255,255,0.5),inset_0_-3px_4px_rgba(0,0,0,0.25),0_3px_6px_rgba(0,0,0,0.25)] transition-[transform,box-shadow,border-color] duration-200 will-change-transform [backface-visibility:hidden] group-enabled:group-hover:from-sawo-darker group-enabled:group-hover:to-[#6b4f36] group-enabled:group-hover:shadow-[inset_0_2px_2px_rgba(255,255,255,0.5),inset_0_-3px_4px_rgba(0,0,0,0.25),0_8px_14px_-4px_rgba(0,0,0,0.35)] motion-safe:group-enabled:group-hover:-translate-y-0.5 group-disabled:from-sawo-light group-disabled:to-sawo-dark group-disabled:shadow-sm">
            <svg className="block" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </span>
        </button>
      </form>
    </div>
  );
}
