"use client";

import { Fragment, FormEvent, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import OpenRouterModelSelect from "@/components/admin/OpenRouterModelSelect";

interface Settings {
  openrouter_api_key: string;
  openrouter_model: string;
  openrouter_embedding_model: string;
  fallback_message: string;
  confidence_threshold: number;
  top_k: number;
  off_topic_threshold: number;
  off_topic_message: string;
  max_sitemap_urls: number;
}

const MAX_SITEMAP_URLS_MIN = 10;
const MAX_SITEMAP_URLS_MAX = 100_000_000;

interface ModelUsage {
  model: string;
  is_free: boolean;
  requests_total: number;
  tokens_total: number;
  cost_total_usd: number;
  requests_today: number;
  tokens_today: number;
  cost_today_usd: number;
  last_used_at: string | null;
}

interface DailyUsage {
  day: string;
  requests: number;
  tokens: number;
  cost_usd: number;
}

function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return `<$0.0001`;
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

interface ResetTarget {
  key: string;
  label: string;
  endpoint: string;
}

const RESET_TARGETS: ResetTarget[] = [
  { key: "chat_logs", label: "Chat Logs", endpoint: "/api/logs" },
  { key: "unanswered", label: "Unanswered", endpoint: "/api/unanswered" },
  { key: "categories", label: "Categories", endpoint: "/api/categories" },
  { key: "faqs", label: "FAQs", endpoint: "/api/faqs" },
  { key: "library", label: "Library", endpoint: "/api/library" },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<"general" | "data">("general");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsage[] | null>(null);
  const [expandedModel, setExpandedModel] = useState<string | null>(null);
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[] | null>(null);
  const [dailyLoading, setDailyLoading] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resettingKey, setResettingKey] = useState<string | null>(null);
  const [resetMessage, setResetMessage] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  function loadUsage() {
    apiGet<ModelUsage[]>("/api/usage/models").then(setModelUsage);
  }

  async function toggleModel(model: string) {
    if (expandedModel === model) {
      setExpandedModel(null);
      setDailyUsage(null);
      return;
    }
    setExpandedModel(model);
    setDailyUsage(null);
    setDailyLoading(true);
    try {
      const data = await apiGet<DailyUsage[]>(`/api/usage/models/daily?model=${encodeURIComponent(model)}`);
      setDailyUsage(data);
    } finally {
      setDailyLoading(false);
    }
  }

  useEffect(() => {
    apiGet<Settings>("/api/settings").then(setSettings);
    loadUsage();
    const interval = setInterval(loadUsage, 30000);
    return () => clearInterval(interval);
  }, []);

  async function handleReset(target: ResetTarget) {
    if (!confirm(`Permanently delete ALL ${target.label} data? This cannot be undone.`)) return;
    setResettingKey(target.key);
    setResetError(null);
    setResetMessage(null);
    try {
      await apiDelete(target.endpoint);
      setResetMessage(`${target.label} data has been reset.`);
    } catch (err) {
      setResetError(err instanceof ApiError ? err.message : `Failed to reset ${target.label}`);
    } finally {
      setResettingKey(null);
    }
  }

  if (!settings) return <p className="text-slate-400 dark:text-slate-500">Loading...</p>;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!settings) return;
    if (settings.max_sitemap_urls < MAX_SITEMAP_URLS_MIN || settings.max_sitemap_urls > MAX_SITEMAP_URLS_MAX) {
      setError(`Max Sitemap URLs must be between ${MAX_SITEMAP_URLS_MIN} and ${MAX_SITEMAP_URLS_MAX}.`);
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const payload: Record<string, unknown> = {
        openrouter_model: settings.openrouter_model,
        max_sitemap_urls: settings.max_sitemap_urls,
      };
      if (apiKeyInput.trim()) payload.openrouter_api_key = apiKeyInput.trim();
      const updated = await apiPost<Settings>("/api/settings", payload);
      setSettings(updated);
      setApiKeyInput("");
      setMessage("Settings saved.");
      loadUsage();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800 dark:text-slate-100">Settings</h1>

      <div className="mb-6 flex gap-2 border-b border-slate-200 dark:border-white/10">
        <button
          type="button"
          onClick={() => setActiveTab("general")}
          className={`px-3 py-2 text-sm font-medium ${
            activeTab === "general"
              ? "border-b-2 border-sawo text-sawo-darker dark:border-sawo-light dark:text-sawo-light"
              : "text-slate-500 dark:text-slate-400"
          }`}
        >
          General
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("data")}
          className={`px-3 py-2 text-sm font-medium ${
            activeTab === "data"
              ? "border-b-2 border-sawo text-sawo-darker dark:border-sawo-light dark:text-sawo-light"
              : "text-slate-500 dark:text-slate-400"
          }`}
        >
          Data Management
        </button>
      </div>

      {activeTab === "data" && (
        <div>
          {resetError && (
            <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">
              {resetError}
            </p>
          )}
          {resetMessage && (
            <p className="mb-4 rounded bg-green-50 px-3 py-2 text-sm text-green-800 dark:bg-green-500/15 dark:text-green-300">
              {resetMessage}
            </p>
          )}
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500 dark:bg-white/5 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-2">Data</th>
                  <th className="px-4 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/10">
                {RESET_TARGETS.map((target) => (
                  <tr key={target.key}>
                    <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">{target.label}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleReset(target)}
                        disabled={resettingKey === target.key}
                        className="text-sm font-medium text-red-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-400"
                      >
                        {resettingKey === target.key ? "Resetting..." : "Reset"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "general" && (
        <>
          <form onSubmit={handleSubmit} className="flex max-w-xl flex-col gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">OpenRouter API Key</label>
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={settings.openrouter_api_key || "Not set"}
                className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">OpenRouter Model</label>
              <OpenRouterModelSelect
                value={settings.openrouter_model}
                onChange={(model) => setSettings({ ...settings, openrouter_model: model })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Max Sitemap URLs</label>
              <input
                type="number"
                min={MAX_SITEMAP_URLS_MIN}
                max={MAX_SITEMAP_URLS_MAX}
                value={settings.max_sitemap_urls}
                onChange={(e) => setSettings({ ...settings, max_sitemap_urls: Number(e.target.value) })}
                className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
              />
              <p className="text-xs text-slate-400 dark:text-slate-500">
                Caps how many pages can be crawled in a single batch from Library &gt; Web Crawler &gt;
                &quot;Discover All Pages (sitemap)&quot;. Doesn&apos;t limit how many pages are discovered — only
                how many of them can be queued to crawl at once. Default 10,000; allowed range{" "}
                {MAX_SITEMAP_URLS_MIN.toLocaleString()}–{MAX_SITEMAP_URLS_MAX.toLocaleString()}.
              </p>
            </div>

            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            {message && <p className="text-sm text-green-600 dark:text-green-400">{message}</p>}

            <div className="flex gap-2">
              <button
                type="submit"
                disabled={saving}
                className="rounded bg-sawo px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sawo-dark disabled:opacity-50 dark:bg-sawo-dark dark:hover:bg-sawo-darker"
              >
                {saving ? "Saving..." : "Save Settings"}
              </button>
            </div>
          </form>

          <div className="mt-8">
            <h2 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">AI Usage Monitor</h2>
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="bg-slate-50 text-left text-slate-500 dark:bg-white/5 dark:text-slate-400">
                  <tr>
                    <th className="px-4 py-2" rowSpan={2}>
                      Model
                    </th>
                    <th className="border-l border-slate-200 px-4 py-1 text-center dark:border-white/10" colSpan={2}>
                      Today
                    </th>
                    <th className="border-l border-slate-200 px-4 py-1 text-center dark:border-white/10" colSpan={3}>
                      All time
                    </th>
                  </tr>
                  <tr className="text-xs">
                    <th className="border-l border-slate-200 px-4 py-1 font-normal dark:border-white/10">Requests</th>
                    <th className="px-4 py-1 font-normal">Tokens</th>
                    <th className="border-l border-slate-200 px-4 py-1 font-normal dark:border-white/10">Requests</th>
                    <th className="px-4 py-1 font-normal">Tokens</th>
                    <th className="px-4 py-1 font-normal">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {(modelUsage ?? []).map((m) => (
                    <Fragment key={m.model}>
                      <tr
                        onClick={() => toggleModel(m.model)}
                        className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
                      >
                        <td className="px-4 py-2">
                          <div className="flex min-w-0 items-center gap-2">
                            <span className="shrink-0 text-slate-400 dark:text-slate-500">{expandedModel === m.model ? "▾" : "▸"}</span>
                            <span className="truncate font-medium text-slate-800 dark:text-slate-100" title={m.model}>
                              {m.model}
                            </span>
                            <span
                              className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
                                m.is_free
                                  ? "bg-green-50 text-green-700 dark:bg-green-500/15 dark:text-green-300"
                                  : "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300"
                              }`}
                            >
                              {m.is_free ? "Free" : "Paid"}
                            </span>
                          </div>
                        </td>
                        <td className="border-l border-slate-100 px-4 py-2 dark:border-white/10">{m.requests_today}</td>
                        <td className="px-4 py-2">{m.tokens_today.toLocaleString()}</td>
                        <td className="border-l border-slate-100 px-4 py-2 dark:border-white/10">{m.requests_total}</td>
                        <td className="px-4 py-2">{m.tokens_total.toLocaleString()}</td>
                        <td className="px-4 py-2">{formatCost(m.cost_total_usd)}</td>
                      </tr>
                      {expandedModel === m.model && (
                        <tr key={`${m.model}-detail`} className="border-t border-slate-100 bg-slate-50 dark:border-white/10 dark:bg-white/5">
                          <td colSpan={6} className="px-4 py-3">
                            {m.is_free && (
                              <p className="mb-3 text-xs text-slate-400 dark:text-slate-500">
                                Free OpenRouter models are rate-limited (typically 20 requests/min,
                                200-1000/day) rather than billed — cost is always $0 for this model; token
                                counts below are for tracking that quota.
                              </p>
                            )}
                            {dailyLoading && <p className="text-xs text-slate-400 dark:text-slate-500">Loading daily breakdown...</p>}
                            {!dailyLoading && dailyUsage && dailyUsage.length === 0 && (
                              <p className="text-xs text-slate-400 dark:text-slate-500">No usage recorded yet.</p>
                            )}
                            {!dailyLoading && dailyUsage && dailyUsage.length > 0 && (
                              <table className="w-full max-w-md text-xs">
                                <thead className="text-left text-slate-500 dark:text-slate-400">
                                  <tr>
                                    <th className="py-1 pr-4 font-normal">Day</th>
                                    <th className="py-1 pr-4 font-normal">Requests</th>
                                    <th className="py-1 pr-4 font-normal">Tokens</th>
                                    <th className="py-1 pr-4 font-normal">Cost</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {dailyUsage.map((d) => (
                                    <tr key={d.day} className="border-t border-slate-200 dark:border-white/10">
                                      <td className="py-1 pr-4">{d.day}</td>
                                      <td className="py-1 pr-4">{d.requests}</td>
                                      <td className="py-1 pr-4">{d.tokens.toLocaleString()}</td>
                                      <td className="py-1 pr-4">{formatCost(d.cost_usd)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                  {modelUsage && modelUsage.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-6 text-center text-slate-400 dark:text-slate-500">
                        No AI usage recorded yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
