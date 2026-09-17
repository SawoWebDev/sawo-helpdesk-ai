"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { apiGet } from "@/lib/api";

interface ModelCatalogEntry {
  id: string;
  provider: string;
  name: string;
  description: string | null;
  context_length: number | null;
  price_per_m_input: number | null;
  price_per_m_output: number | null;
  tier: "cheap" | "balanced" | "premium" | null;
  recommended: boolean;
}

// Brand icons via Simple Icons' free CDN (an <img> that just disappears on
// error rather than showing a broken-image glyph if a slug doesn't exist or
// the CDN is unreachable — the provider label is always shown as text too,
// so identification never actually depends on the icon loading).
// "openai" is the one exception: cdn.simpleicons.org 404s on that slug (a
// trademark-driven removal), so it's self-hosted at
// /public/assets/icons/openai.svg instead (Simple Icons is CC0-licensed).
// It can't be recolored via URL like the others, so it renders in its
// default black on a small white chip so it stays legible in dark mode too.
const PROVIDER_META: Record<string, { label: string; icon: string | null }> = {
  openai: { label: "OpenAI", icon: "/assets/icons/openai.svg" },
  anthropic: { label: "Anthropic", icon: "https://cdn.simpleicons.org/anthropic/191919" },
  google: { label: "Google", icon: "https://cdn.simpleicons.org/google/4285F4" },
  deepseek: { label: "DeepSeek", icon: "https://cdn.simpleicons.org/deepseek/4D6BFE" },
};

function providerMeta(id: string) {
  const key = id.split("/")[0];
  return PROVIDER_META[key] || { label: key, icon: null };
}

// A simple, at-a-glance price-tier badge — mirrors the backend's own
// classification (app/services/model_catalog.py) so the label always
// matches the tier it's showing.
const TIER_META: Record<string, { label: string; classes: string }> = {
  cheap: { label: "Cheap & efficient", classes: "text-green-700 border-green-300 dark:text-green-300 dark:border-green-500/40" },
  balanced: { label: "Balanced", classes: "text-amber-700 border-amber-300 dark:text-amber-300 dark:border-amber-500/40" },
  premium: { label: "Premium · high reliability", classes: "text-red-600 border-slate-300 dark:text-red-400 dark:border-white/15" },
};

function money(n: number | null): string | null {
  if (n == null) return null;
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

// Full words, not abbreviations — "1.05M context", not "1M ctx".
function formatContextLength(n: number | null): string | null {
  if (n == null) return null;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2).replace(/\.?0+$/, "")}M context`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}K context`;
  return `${n} context`;
}

function detailLine(m: ModelCatalogEntry): string {
  const parts: string[] = [];
  const ctx = formatContextLength(m.context_length);
  if (ctx) parts.push(ctx);
  if (m.price_per_m_input != null) parts.push(`${money(m.price_per_m_input)}/M input tokens`);
  if (m.price_per_m_output != null) parts.push(`${money(m.price_per_m_output)}/M output tokens`);
  return parts.length ? parts.join(" · ") : "Pricing unavailable";
}

export default function OpenRouterModelSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [customMode, setCustomMode] = useState(false);
  const [customValue, setCustomValue] = useState(value);
  const [catalog, setCatalog] = useState<ModelCatalogEntry[] | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  function loadCatalog() {
    setCatalogError(false);
    apiGet<ModelCatalogEntry[]>("/api/settings/models")
      .then(setCatalog)
      .catch(() => setCatalogError(true));
  }

  // Fetched proactively (not just lazily on dropdown-open) so the trigger
  // can upgrade from the bare id to the real bold name without requiring
  // the admin to open the picker first.
  useEffect(() => {
    loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCustomMode(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const selected = catalog?.find((m) => m.id === value);

  function selectModel(id: string) {
    onChange(id);
    setOpen(false);
    setCustomMode(false);
  }

  function applyCustom() {
    const trimmed = customValue.trim();
    if (trimmed) selectModel(trimmed);
  }

  return (
    <div className="relative" ref={wrapperRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2.5 rounded border border-slate-300 px-3 py-2 text-left text-sm transition-colors hover:border-sawo/50 dark:border-white/15 dark:bg-white/5 dark:hover:border-sawo-light/40"
      >
        <span className="min-w-0 flex-1 truncate">
          {!value ? (
            <span className="text-slate-400 dark:text-slate-500">Select a model…</span>
          ) : selected ? (
            <strong className="font-semibold text-slate-800 dark:text-slate-100">{selected.name}</strong>
          ) : (
            <span className="text-slate-700 dark:text-slate-200">{value}</span>
          )}
        </span>
        <ChevronDown size={16} className={`shrink-0 text-slate-400 transition-transform dark:text-slate-500 ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute z-20 mt-1.5 max-h-96 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white p-1.5 shadow-xl dark:border-white/10 dark:bg-night-surface"
        >
          {!catalog && !catalogError && (
            <div className="px-3 py-6 text-center text-xs text-slate-400 dark:text-slate-500">Loading models…</div>
          )}
          {catalogError && (
            <div className="px-3 py-6 text-center text-xs text-slate-400 dark:text-slate-500">
              Could not load models.{" "}
              <button type="button" onClick={loadCatalog} className="font-medium text-sawo-dark hover:underline dark:text-sawo-light">
                Retry
              </button>
            </div>
          )}
          {catalog?.map((m) => {
            const provider = providerMeta(m.id);
            const tier = !m.recommended && m.tier ? TIER_META[m.tier] : null;
            return (
              <button
                key={m.id}
                type="button"
                role="option"
                aria-selected={m.id === value}
                onClick={() => selectModel(m.id)}
                className={`mb-0.5 block w-full rounded-md px-2.5 py-2 text-left transition-colors hover:bg-slate-50 dark:hover:bg-white/5 ${
                  m.id === value ? "ring-1 ring-inset ring-sawo/40" : ""
                } ${
                  m.recommended
                    ? "bg-green-50/70 hover:bg-green-50 dark:bg-green-500/10 dark:hover:bg-green-500/15"
                    : ""
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="inline-flex min-w-0 items-center gap-1.5">
                    {provider.icon && (
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-white p-0.5">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={provider.icon}
                          alt=""
                          className="h-full w-full object-contain"
                          onError={(e) => (e.currentTarget.style.display = "none")}
                        />
                      </span>
                    )}
                    <span className="truncate text-[13.5px] font-bold text-slate-800 dark:text-slate-100">{m.name}</span>
                  </span>
                  {m.recommended && (
                    <span className="shrink-0 rounded-full border border-green-300 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-green-700 dark:border-green-500/40 dark:text-green-300">
                      Recommended · cost-efficient
                    </span>
                  )}
                  {tier && (
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${tier.classes}`}>
                      {tier.label}
                    </span>
                  )}
                </div>
                {m.description && <div className="mt-0.5 text-xs leading-snug text-slate-500 dark:text-slate-400">{m.description}</div>}
                <div className="mt-1 text-[11.5px] font-medium text-slate-700 dark:text-slate-300">{detailLine(m)}</div>
                <div className="mt-0.5 font-mono text-[10.5px] text-slate-400 dark:text-slate-500">
                  {provider.label} · {m.id}
                </div>
              </button>
            );
          })}

          <div className="mt-0.5 border-t border-slate-100 pt-1.5 dark:border-white/10">
            {!customMode ? (
              <button
                type="button"
                role="option"
                onClick={() => {
                  setCustomMode(true);
                  setCustomValue(value);
                }}
                className="block w-full rounded-md px-2.5 py-2 text-left hover:bg-slate-50 dark:hover:bg-white/5"
              >
                <span className="text-[13.5px] font-bold text-slate-800 dark:text-slate-100">Custom model ID…</span>
                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Type any OpenRouter model id directly.</div>
              </button>
            ) : (
              <div className="flex gap-1.5 px-1 py-1">
                <input
                  autoFocus
                  value={customValue}
                  onChange={(e) => setCustomValue(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && applyCustom()}
                  placeholder="provider/model-id"
                  className="flex-1 rounded border border-slate-300 px-2 py-1 text-xs dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
                />
                <button
                  type="button"
                  onClick={applyCustom}
                  className="shrink-0 rounded bg-sawo px-2 py-1 text-xs font-medium text-white dark:bg-sawo-dark"
                >
                  Use
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
