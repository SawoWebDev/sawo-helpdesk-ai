"use client";

import { useEffect, useId, useState } from "react";
import { Sparkles } from "lucide-react";
import { apiGet } from "@/lib/api";
import BotAvatar from "./BotAvatar";
import { DocumentIcon, HrIcon, ItIcon, ProcessesIcon, ProductIcon, SalesIcon } from "./TopicIcons";

interface PopularQuestionsResponse {
  items: { question: string; source: "usage" | "faq" }[];
  based_on_usage: boolean;
}

interface TopicCard {
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  title: string;
  description: string;
  /**
   * Concrete, staff-phrased questions grounded in what the knowledge base
   * actually contains for this topic (see WelcomeCards test/report for the
   * evidence behind each one). Kept to ~3 so the panel stays scannable.
   */
  suggestions: string[];
}

const CARDS: TopicCard[] = [
  {
    icon: <ProcessesIcon />,
    iconBg: "bg-gradient-to-br from-amber-100 to-amber-300",
    iconColor: "text-amber-700",
    title: "Troubleshooting & Error Codes",
    description: "Error codes, heater faults, and controller issues.",
    suggestions: [
      "My heater controller shows error E1 — what causes it and how do I fix it?",
      "The display shows \"oPEn\" and the heater won't start — what's wrong?",
      "My heater is making a loud humming noise — what's causing it?",
    ],
  },
  {
    icon: <ProductIcon />,
    iconBg: "bg-gradient-to-br from-rose-100 to-rose-300",
    iconColor: "text-rose-700",
    title: "Product Specs & Compatibility",
    description: "Heater series, models, sizing, and specs.",
    suggestions: [
      "What are all our sauna heater series and their specs?",
      "Can you list all our Aries Tower heater models?",
      "What are the specs for the Scandifire Red NS heater?",
    ],
  },
  {
    icon: <SalesIcon />,
    iconBg: "bg-gradient-to-br from-blue-100 to-blue-300",
    iconColor: "text-blue-700",
    title: "Customer & Sales Questions",
    description: "Company facts and product info for customer calls.",
    suggestions: [
      "What is SAWO and what products do we offer?",
      "Does SAWO have a sustainability commitment I can share with a customer?",
      "What series does our sauna heater lineup include that I can explain to a customer?",
    ],
  },
  {
    icon: <DocumentIcon />,
    iconBg: "bg-gradient-to-br from-teal-100 to-teal-300",
    iconColor: "text-teal-700",
    title: "Manuals & Technical Documents",
    description: "Installation, wiring, and controller compatibility.",
    suggestions: [
      "What are the installation and wiring requirements for the Innova 2.0 Power Controller?",
      "Is the Innova Classic Built-In compatible with heaters over 15kW?",
      "What's involved in installing the Saunova 2.0 Built-In controller?",
    ],
  },
  {
    icon: <ItIcon />,
    iconBg: "bg-gradient-to-br from-emerald-100 to-emerald-300",
    iconColor: "text-emerald-700",
    title: "IT & Access Issues",
    description: "Login, account access, and internal systems.",
    suggestions: [
      "Who do I contact for IT access or system issues?",
      "Who do I contact if I can't log into an internal system?",
      "Which team handles requests for new software or tools?",
    ],
  },
  {
    icon: <HrIcon />,
    iconBg: "bg-gradient-to-br from-purple-100 to-purple-300",
    iconColor: "text-purple-700",
    title: "Company Policies & Procedures",
    description: "Leave, benefits, approvals, and who to ask.",
    suggestions: [
      "What's our company policy on requesting leave?",
      "What's the process for getting an expense approved?",
      "Who should I contact about benefits questions?",
    ],
  },
];

export default function WelcomeCards({
  onSelect,
  disabled,
}: {
  onSelect: (text: string) => void;
  disabled: boolean;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const panelId = useId();
  const active = activeIndex !== null ? CARDS[activeIndex] : null;

  const [popular, setPopular] = useState<PopularQuestionsResponse | null>(null);

  useEffect(() => {
    apiGet<PopularQuestionsResponse>("/api/chat/popular-questions?limit=4")
      .then(setPopular)
      .catch(() => setPopular(null));
  }, []);

  function toggleCard(index: number) {
    setActiveIndex((prev) => (prev === index ? null : index));
  }

  function handleSuggestion(text: string) {
    setActiveIndex(null);
    onSelect(text);
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-6 px-4 py-8 text-center">
      <BotAvatar className="h-16 w-16 rounded-full shadow-sm" />

      <div className="space-y-1.5">
        <h2 className="text-xl font-bold text-slate-800 dark:text-white">SAWO Helpdesk</h2>
        <p className="mx-auto max-w-xs text-sm text-slate-500 dark:text-slate-400">
          Internal help for SAWO teams. Ask a question or pick a topic below.
        </p>
      </div>

      <div className="grid w-full grid-cols-2 gap-3 sm:grid-cols-3">
        {CARDS.map((item, index) => (
          <button
            key={item.title}
            type="button"
            disabled={disabled}
            aria-expanded={activeIndex === index}
            aria-controls={activeIndex === index ? panelId : undefined}
            onClick={() => toggleCard(index)}
            className="group relative rounded-2xl text-left disabled:opacity-50"
          >
            {/* The button stays put and owns the hover; only this face lifts, so the
                pointer never slips off the bottom edge mid-lift and makes it shake. */}
            <span
              data-reveal-hit="lift"
              className={`glass glass-hover glass-hover-no-glow relative flex h-full w-full flex-col items-start gap-2 rounded-2xl border bg-gradient-to-br from-white to-sawo-bg p-3 shadow-[inset_0_1px_1px_rgba(255,255,255,0.9),inset_0_-2px_4px_-1px_rgba(139,105,71,0.15),0_10px_18px_-12px_rgba(139,105,71,0.35),0_2px_3px_-1px_rgba(139,105,71,0.12)] transition-[transform,box-shadow,border-color] duration-200 will-change-transform [backface-visibility:hidden] group-enabled:group-hover:shadow-[inset_0_1px_1px_rgba(255,255,255,1),inset_0_-2px_4px_-1px_rgba(139,105,71,0.2),0_18px_30px_-14px_rgba(139,105,71,0.45),0_4px_8px_-2px_rgba(139,105,71,0.18)] motion-safe:group-enabled:group-hover:-translate-y-1 ${
                activeIndex === index
                  ? "border-sawo/60 shadow-[inset_0_1px_1px_rgba(255,255,255,1),inset_0_-2px_4px_-1px_rgba(139,105,71,0.2),0_18px_30px_-14px_rgba(139,105,71,0.45),0_4px_8px_-2px_rgba(139,105,71,0.18)]"
                  : "border-transparent group-enabled:group-hover:border-sawo/50"
              }`}
            >
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl p-2.5 shadow-[inset_0_1px_1px_rgba(255,255,255,0.7),inset_0_-2px_3px_rgba(0,0,0,0.12),0_2px_4px_rgba(0,0,0,0.12)] dark:shadow-[inset_0_1px_1px_rgba(255,255,255,0.4),inset_0_-2px_3px_rgba(0,0,0,0.3),0_0_14px_-3px_rgba(0,0,0,0.5)] ${item.iconBg} ${item.iconColor}`}
              >
                {item.icon}
              </span>
              <span className="text-[13px] font-semibold leading-tight text-slate-700 dark:text-slate-100">{item.title}</span>
              <span className="text-[11px] leading-snug text-slate-400 dark:text-slate-500">{item.description}</span>
              {/* Same sweeping glare as the input (see .glass-edge-wide in globals.css),
                  just triggered by hover instead of focus. Nested inside the lifting
                  face (not the stationary button) so it rides along with the lift
                  instead of staying behind. */}
              <span
                aria-hidden
                className="glass-edge glass-edge-wide pointer-events-none absolute inset-0 rounded-2xl"
              />
            </span>
          </button>
        ))}
      </div>

      {popular && popular.items.length > 0 && (
        <div className="w-full text-left">
          <p className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            {popular.based_on_usage ? "Popular questions" : "Suggested questions"}
          </p>
          <div className="flex flex-col gap-1.5">
            {popular.items.map((item) => (
              <button
                key={item.question}
                type="button"
                disabled={disabled}
                onClick={() => handleSuggestion(item.question)}
                className="group relative w-full rounded-xl text-left disabled:opacity-50"
              >
                <span className="glass glass-hover glass-hover-no-glow relative flex w-full items-center gap-2.5 rounded-xl border border-transparent bg-gradient-to-br from-white to-sawo-bg px-3 py-2 shadow-[inset_0_1px_1px_rgba(255,255,255,0.9),inset_0_-2px_4px_-1px_rgba(139,105,71,0.12),0_6px_14px_-10px_rgba(139,105,71,0.35)] transition-[border-color,box-shadow] duration-200 group-enabled:group-hover:border-sawo/40">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sawo/15 text-sawo-dark dark:text-slate-300">
                    <Sparkles size={12} />
                  </span>
                  <span className="truncate text-[12.5px] leading-snug text-slate-600 dark:text-slate-200">
                    {item.question}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {active && (
        <div
          id={panelId}
          role="group"
          aria-label={`Suggested questions for ${active.title}`}
          className="glass glass-edge w-full rounded-2xl border border-sawo/25 bg-white p-3 text-left shadow-sm"
        >
          <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            {active.title}
          </p>
          <div className="flex flex-col gap-1.5">
            {active.suggestions.map((text) => (
              <button
                key={text}
                type="button"
                disabled={disabled}
                onClick={() => handleSuggestion(text)}
                className="glass-hover w-full rounded-xl px-3 py-2 text-left text-[13px] leading-snug text-slate-700 transition-colors hover:bg-sawo/10 disabled:opacity-50 dark:text-slate-100"
              >
                {text}
              </button>
            ))}
            <button
              type="button"
              disabled={disabled}
              onClick={() => setActiveIndex(null)}
              className="w-full rounded-xl px-3 py-2 text-left text-[13px] font-medium text-sawo-dark underline-offset-2 hover:underline disabled:opacity-50 dark:text-sawo-light"
            >
              Ask something else
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
