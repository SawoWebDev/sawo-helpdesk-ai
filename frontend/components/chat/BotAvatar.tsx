"use client";

import { useId } from "react";

const BAND = "M6.2 11.6V10a5.8 5.8 0 0 1 11.6 0v1.6";
const BOOM = "M17.9 14.6v.2a2.4 2.4 0 0 1-2.4 2.4h-1.4";

export default function BotAvatar({ className = "h-7 w-7 rounded-md" }: { className?: string }) {
  const maskId = `agent-cut-${useId().replace(/:/g, "")}`;

  return (
    <span
      data-reveal-hit="pop"
      className={`glass-brown glass-edge relative flex shrink-0 items-center justify-center bg-gradient-to-br from-sawo-light to-sawo-dark text-white shadow-[inset_0_2px_2px_rgba(255,255,255,0.5),inset_0_-3px_4px_rgba(0,0,0,0.25),0_3px_6px_rgba(0,0,0,0.2)] ${className}`}
    >
      <svg viewBox="0 0 24 24" className="h-[64%] w-[64%]" fill="currentColor" aria-hidden>
        {/* Cut a gap into the head and shoulders wherever the headset crosses them,
            so the white headset stays readable on top of the white figure */}
        <mask id={maskId}>
          <rect width="24" height="24" fill="white" />
          <path d={BOOM} fill="none" stroke="black" strokeWidth="3.4" strokeLinecap="round" />
          <circle cx="13.6" cy="17.2" r="2.2" fill="black" />
        </mask>
        <g mask={`url(#${maskId})`}>
          <circle cx="12" cy="9.8" r="4" />
          <path d="M3.8 21.3c0-4.1 3.7-6.6 8.2-6.6s8.2 2.5 8.2 6.6a.8.8 0 0 1-.8.8H4.6a.8.8 0 0 1-.8-.8Z" />
        </g>
        <path d={BAND} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <rect x="4.5" y="10.3" width="3.1" height="4.5" rx="1.3" />
        <rect x="16.4" y="10.3" width="3.1" height="4.5" rx="1.3" />
        <path d={BOOM} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="13.6" cy="17.2" r="1.15" />
      </svg>
    </span>
  );
}
