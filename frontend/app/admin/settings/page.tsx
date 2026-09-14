"use client";

import { FormEvent, useEffect, useState } from "react";
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

interface UsageSummary {
  active_model: string;
  active_model_is_free: boolean;
  requests_today: number;
  tokens_today: number;
  requests_total: number;
  tokens_total: number;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function loadUsage() {
    apiGet<UsageSummary>("/api/usage/summary").then(setUsage);
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

      {usage && (
        <div className="mt-8 max-w-xl rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700">AI Usage Monitor</h2>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                usage.active_model_is_free ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-600"
              }`}
            >
              {usage.active_model_is_free ? "Free model" : "Paid model"}
            </span>
          </div>
          <p className="mb-4 truncate text-xs text-slate-500" title={usage.active_model}>
            Active model: <span className="font-medium text-slate-700">{usage.active_model || "Not set"}</span>
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded border border-slate-100 p-3">
              <p className="text-xs text-slate-500">Requests today</p>
              <p className="text-xl font-semibold text-slate-800">{usage.requests_today}</p>
            </div>
            <div className="rounded border border-slate-100 p-3">
              <p className="text-xs text-slate-500">Tokens today</p>
              <p className="text-xl font-semibold text-slate-800">{usage.tokens_today.toLocaleString()}</p>
            </div>
            <div className="rounded border border-slate-100 p-3">
              <p className="text-xs text-slate-500">Requests (all time)</p>
              <p className="text-xl font-semibold text-slate-800">{usage.requests_total}</p>
            </div>
            <div className="rounded border border-slate-100 p-3">
              <p className="text-xs text-slate-500">Tokens (all time)</p>
              <p className="text-xl font-semibold text-slate-800">{usage.tokens_total.toLocaleString()}</p>
            </div>
          </div>
          {usage.active_model_is_free && (
            <p className="mt-3 text-xs text-slate-400">
              Free OpenRouter models are rate-limited (typically 20 requests/min, 200-1000/day)
              rather than billed — token counts here are for tracking that quota, not cost.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
