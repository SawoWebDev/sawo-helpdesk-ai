"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";

interface Settings {
  ai_engine: string;
  openrouter_api_key: string;
  openrouter_model: string;
  ollama_base_url: string;
  ollama_generation_model: string;
  ollama_embedding_model: string;
  fallback_message: string;
  confidence_threshold: number;
  top_k: number;
  off_topic_threshold: number;
  off_topic_message: string;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Settings>("/api/settings").then(setSettings);
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
        ai_engine: settings.ai_engine,
        openrouter_model: settings.openrouter_model,
        ollama_base_url: settings.ollama_base_url,
        ollama_generation_model: settings.ollama_generation_model,
        ollama_embedding_model: settings.ollama_embedding_model,
        fallback_message: settings.fallback_message,
        confidence_threshold: settings.confidence_threshold,
        top_k: settings.top_k,
        off_topic_threshold: settings.off_topic_threshold,
        off_topic_message: settings.off_topic_message,
      };
      if (apiKeyInput.trim()) payload.openrouter_api_key = apiKeyInput.trim();
      const updated = await apiPost<Settings>("/api/settings", payload);
      setSettings(updated);
      setApiKeyInput("");
      setMessage("Settings saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleReindex() {
    setReindexing(true);
    setError(null);
    setMessage(null);
    try {
      const res = await apiPost<{ reindexed: number }>("/api/admin/reindex");
      setMessage(`Re-embedded ${res.reindexed} FAQ entries.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reindex failed");
    } finally {
      setReindexing(false);
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800">Settings</h1>

      <form onSubmit={handleSubmit} className="flex max-w-xl flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">Active AI Engine</label>
          <select
            value={settings.ai_engine}
            onChange={(e) => setSettings({ ...settings, ai_engine: e.target.value })}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="ollama">Ollama</option>
            <option value="openrouter">OpenRouter</option>
          </select>
        </div>

        {settings.ai_engine === "openrouter" && (
          <>
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
          </>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">Ollama Base URL</label>
          <input
            value={settings.ollama_base_url}
            onChange={(e) => setSettings({ ...settings, ollama_base_url: e.target.value })}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">Ollama Generation Model</label>
          <input
            value={settings.ollama_generation_model}
            onChange={(e) => setSettings({ ...settings, ollama_generation_model: e.target.value })}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">Ollama Embedding Model</label>
          <input
            value={settings.ollama_embedding_model}
            onChange={(e) => setSettings({ ...settings, ollama_embedding_model: e.target.value })}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
          <p className="text-xs text-slate-400">
            Changing this requires re-indexing all FAQ entries below.
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">Fallback Message</label>
          <textarea
            value={settings.fallback_message}
            onChange={(e) => setSettings({ ...settings, fallback_message: e.target.value })}
            rows={2}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
          <p className="text-xs text-slate-400">
            Shown for genuine support questions the AI can&apos;t answer confidently. These are
            logged under Unanswered Questions for review.
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">Off-Topic Redirect Message</label>
          <textarea
            value={settings.off_topic_message}
            onChange={(e) => setSettings({ ...settings, off_topic_message: e.target.value })}
            rows={2}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
          <p className="text-xs text-slate-400">
            Shown for small talk / greetings unrelated to any product or technical topic (e.g.
            &quot;how are you?&quot;). Not logged for agent review.
          </p>
        </div>

        <div className="flex gap-4">
          <div className="flex flex-1 flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Off-Topic Threshold</label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={settings.off_topic_threshold}
              onChange={(e) => setSettings({ ...settings, off_topic_threshold: Number(e.target.value) })}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <p className="text-xs text-slate-400">Below this similarity: off-topic redirect.</p>
          </div>
          <div className="flex flex-1 flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Confidence Threshold</label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={settings.confidence_threshold}
              onChange={(e) => setSettings({ ...settings, confidence_threshold: Number(e.target.value) })}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <p className="text-xs text-slate-400">Above this similarity: answer from KB.</p>
          </div>
          <div className="flex flex-1 flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Top-K Retrieval</label>
            <input
              type="number"
              min="1"
              max="20"
              value={settings.top_k}
              onChange={(e) => setSettings({ ...settings, top_k: Number(e.target.value) })}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
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
          <button
            type="button"
            onClick={handleReindex}
            disabled={reindexing}
            className="rounded border border-slate-300 px-4 py-2 text-sm disabled:opacity-50"
          >
            {reindexing ? "Re-indexing..." : "Re-index All FAQs"}
          </button>
        </div>
      </form>
    </div>
  );
}
