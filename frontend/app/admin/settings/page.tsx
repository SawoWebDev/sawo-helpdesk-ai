"use client";

import { Fragment, FormEvent, useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";

interface Settings {
  openrouter_api_key: string;
  openrouter_model: string;
  openrouter_embedding_model: string;
  fallback_message: string;
  confidence_threshold: number;
  top_k: number;
  off_topic_threshold: number;
  off_topic_message: string;
}

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

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsage[] | null>(null);
  const [expandedModel, setExpandedModel] = useState<string | null>(null);
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[] | null>(null);
  const [dailyLoading, setDailyLoading] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (!settings) return <p className="text-slate-400">Loading...</p>;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const payload: Record<string, unknown> = {
        openrouter_model: settings.openrouter_model,
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
      <h1 className="mb-6 text-xl font-semibold text-slate-800">Settings</h1>

      <form onSubmit={handleSubmit} className="flex max-w-xl flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">OpenRouter API Key</label>
          <input
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder={settings.openrouter_api_key || "Not set"}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">OpenRouter Model</label>
          <input
            value={settings.openrouter_model}
            onChange={(e) => setSettings({ ...settings, openrouter_model: e.target.value })}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {message && <p className="text-sm text-green-600">{message}</p>}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </form>

      <div className="mt-8">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">AI Usage Monitor</h2>
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-2" rowSpan={2}>
                  Model
                </th>
                <th className="border-l border-slate-200 px-4 py-1 text-center" colSpan={2}>
                  Today
                </th>
                <th className="border-l border-slate-200 px-4 py-1 text-center" colSpan={3}>
                  All time
                </th>
              </tr>
              <tr className="text-xs">
                <th className="border-l border-slate-200 px-4 py-1 font-normal">Requests</th>
                <th className="px-4 py-1 font-normal">Tokens</th>
                <th className="border-l border-slate-200 px-4 py-1 font-normal">Requests</th>
                <th className="px-4 py-1 font-normal">Tokens</th>
                <th className="px-4 py-1 font-normal">Cost</th>
              </tr>
            </thead>
            <tbody>
              {(modelUsage ?? []).map((m) => (
                <Fragment key={m.model}>
                  <tr
                    onClick={() => toggleModel(m.model)}
                    className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                  >
                    <td className="px-4 py-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="shrink-0 text-slate-400">{expandedModel === m.model ? "▾" : "▸"}</span>
                        <span className="truncate font-medium text-slate-800" title={m.model}>
                          {m.model}
                        </span>
                        <span
                          className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
                            m.is_free ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {m.is_free ? "Free" : "Paid"}
                        </span>
                      </div>
                    </td>
                    <td className="border-l border-slate-100 px-4 py-2">{m.requests_today}</td>
                    <td className="px-4 py-2">{m.tokens_today.toLocaleString()}</td>
                    <td className="border-l border-slate-100 px-4 py-2">{m.requests_total}</td>
                    <td className="px-4 py-2">{m.tokens_total.toLocaleString()}</td>
                    <td className="px-4 py-2">{formatCost(m.cost_total_usd)}</td>
                  </tr>
                  {expandedModel === m.model && (
                    <tr key={`${m.model}-detail`} className="border-t border-slate-100 bg-slate-50">
                      <td colSpan={6} className="px-4 py-3">
                        {m.is_free && (
                          <p className="mb-3 text-xs text-slate-400">
                            Free OpenRouter models are rate-limited (typically 20 requests/min,
                            200-1000/day) rather than billed — cost is always $0 for this model; token
                            counts below are for tracking that quota.
                          </p>
                        )}
                        {dailyLoading && <p className="text-xs text-slate-400">Loading daily breakdown...</p>}
                        {!dailyLoading && dailyUsage && dailyUsage.length === 0 && (
                          <p className="text-xs text-slate-400">No usage recorded yet.</p>
                        )}
                        {!dailyLoading && dailyUsage && dailyUsage.length > 0 && (
                          <table className="w-full max-w-md text-xs">
                            <thead className="text-left text-slate-500">
                              <tr>
                                <th className="py-1 pr-4 font-normal">Day</th>
                                <th className="py-1 pr-4 font-normal">Requests</th>
                                <th className="py-1 pr-4 font-normal">Tokens</th>
                                <th className="py-1 pr-4 font-normal">Cost</th>
                              </tr>
                            </thead>
                            <tbody>
                              {dailyUsage.map((d) => (
                                <tr key={d.day} className="border-t border-slate-200">
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
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                    No AI usage recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
