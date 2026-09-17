"use client";

import BotAvatar from "./BotAvatar";
import { HrIcon, ItIcon, MarketingIcon, ProcessesIcon, ProductIcon, SalesIcon } from "./TopicIcons";

interface Suggestion {
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  title: string;
  description: string;
  prompt: string;
}

const SUGGESTIONS: Suggestion[] = [
  {
    icon: <SalesIcon />,
    iconBg: "bg-gradient-to-br from-blue-100 to-blue-300",
    iconColor: "text-blue-700",
    title: "Sales",
    description: "Pricing, quotes, and deal support.",
    prompt: "What's our current pricing and quoting process for a new deal?",
  },
  {
    icon: <MarketingIcon />,
    iconBg: "bg-gradient-to-br from-orange-100 to-orange-300",
    iconColor: "text-orange-700",
    title: "Marketing",
    description: "Brand assets, campaigns, and messaging.",
    prompt: "Where can I find our latest brand assets and marketing guidelines?",
  },
  {
    icon: <HrIcon />,
    iconBg: "bg-gradient-to-br from-purple-100 to-purple-300",
    iconColor: "text-purple-700",
    title: "HR & Policies",
    description: "Leave, benefits, and company policies.",
    prompt: "What's our company policy on requesting leave?",
  },
  {
    icon: <ItIcon />,
    iconBg: "bg-gradient-to-br from-emerald-100 to-emerald-300",
    iconColor: "text-emerald-700",
    title: "IT Support",
    description: "Access, tools, and internal systems.",
    prompt: "Who do I contact for IT access or system issues?",
  },
  {
    icon: <ProductIcon />,
    iconBg: "bg-gradient-to-br from-rose-100 to-rose-300",
    iconColor: "text-rose-700",
    title: "Product Knowledge",
    description: "Specs and details to answer client questions.",
    prompt: "Where can I find detailed specs on our products?",
  },
  {
    icon: <ProcessesIcon />,
    iconBg: "bg-gradient-to-br from-amber-100 to-amber-300",
    iconColor: "text-amber-700",
    title: "Internal Processes",
    description: "SOPs, approvals, and who to ask.",
    prompt: "What's the internal process and who should I contact for approvals?",
  },
];

export default function WelcomeCards({
  onSelect,
  disabled,
}: {
  onSelect: (text: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-6 px-4 py-8 text-center">
      <BotAvatar className="h-16 w-16 rounded-full shadow-sm" />

      <div className="space-y-1.5">
        <h2 className="text-xl font-bold text-slate-800 dark:text-white">Welcome to SAWO Helpdesk</h2>
        <p className="mx-auto max-w-xs text-sm text-slate-500 dark:text-slate-400">
          Internal help for SAWO teams. Ask a question or pick a topic below.
        </p>
      </div>

      <div className="grid w-full grid-cols-2 gap-3 sm:grid-cols-3">
        {SUGGESTIONS.map((item) => (
          <button
            key={item.title}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(item.prompt)}
            className="group rounded-2xl text-left disabled:opacity-50"
          >
            {/* The button stays put and owns the hover; only this face lifts, so the
                pointer never slips off the bottom edge mid-lift and makes it shake. */}
            <span data-reveal-hit="lift" className="glass glass-edge glass-hover relative flex h-full w-full flex-col items-start gap-2 rounded-2xl border border-sawo/25 bg-white p-3 shadow-sm transition-[transform,box-shadow,border-color] duration-200 will-change-transform [backface-visibility:hidden] group-enabled:group-hover:border-sawo/50 group-enabled:group-hover:shadow-lg motion-safe:group-enabled:group-hover:-translate-y-1">
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl p-2.5 shadow-[inset_0_1px_1px_rgba(255,255,255,0.7),inset_0_-2px_3px_rgba(0,0,0,0.12),0_2px_4px_rgba(0,0,0,0.12)] dark:shadow-[inset_0_1px_1px_rgba(255,255,255,0.4),inset_0_-2px_3px_rgba(0,0,0,0.3),0_0_14px_-3px_rgba(0,0,0,0.5)] ${item.iconBg} ${item.iconColor}`}
              >
                {item.icon}
              </span>
              <span className="text-[13px] font-semibold leading-tight text-slate-700 dark:text-slate-100">{item.title}</span>
              <span className="text-[11px] leading-snug text-slate-400 dark:text-slate-500">{item.description}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
