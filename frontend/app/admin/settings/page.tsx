"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { apiDelete, apiGet, apiPost, downloadFile, getToken, ApiError } from "@/lib/api";
import OpenRouterModelSelect from "@/components/admin/OpenRouterModelSelect";

// Matches the backend's settings.py MASK constant — the API never returns
// the real key, only this sentinel when one is saved.
const OPENROUTER_KEY_MASK = "********";

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
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [editingKey, setEditingKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resettingKey, setResettingKey] = useState<string | null>(null);
  const [resetMessage, setResetMessage] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [kbExporting, setKbExporting] = useState(false);
  const [kbImporting, setKbImporting] = useState(false);
  const [kbMessage, setKbMessage] = useState<string | null>(null);
  const [kbError, setKbError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Settings>("/api/settings").then((s) => {
      setSettings(s);
      setEditingKey(!s.openrouter_api_key);
    });
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

  async function handleExportKnowledgeBase() {
    setKbError(null);
    setKbMessage(null);
    setKbExporting(true);
    try {
      await downloadFile("/api/knowledge-base/export", "knowledge_base_export.xlsx");
    } catch (err) {
      setKbError(err instanceof ApiError ? err.message : "Failed to export knowledge base");
    } finally {
      setKbExporting(false);
    }
  }

  async function handleImportKnowledgeBase(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setKbError(null);
    setKbMessage(null);
    setKbImporting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const token = getToken();
      const res = await fetch("/api/knowledge-base/import", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new ApiError(res.status, data.detail ?? "Failed to import knowledge base");
      }
      const faqErrors = data.faqs.errors.length;
      const libraryErrors = data.library.errors.length;
      setKbMessage(
        `FAQs — created: ${data.faqs.created}, skipped: ${data.faqs.skipped}, failed: ${data.faqs.failed}. ` +
          `Library — created: ${data.library.created}, skipped: ${data.library.skipped}, failed: ${data.library.failed}.` +
          (faqErrors || libraryErrors ? " See console for row errors." : "")
      );
      if (faqErrors) console.table(data.faqs.errors);
      if (libraryErrors) console.table(data.library.errors);
    } catch (err) {
      setKbError(err instanceof ApiError ? err.message : "Failed to import knowledge base");
    } finally {
      setKbImporting(false);
      e.target.value = "";
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
      if (editingKey && apiKeyInput.trim() && apiKeyInput !== OPENROUTER_KEY_MASK) {
        payload.openrouter_api_key = apiKeyInput.trim();
      }
      const updated = await apiPost<Settings>("/api/settings", payload);
      setSettings(updated);
      setApiKeyInput("");
      setEditingKey(!updated.openrouter_api_key);
      setMessage("Settings saved.");
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
          <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface">
            <h2 className="mb-1 text-sm font-semibold text-slate-800 dark:text-slate-100">Knowledge Base Backup</h2>
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
              Export every FAQ and Library entry into one Excel file, or import one to restore or move a knowledge
              base to another deployment without recrawling.
            </p>
            {kbMessage && (
              <p className="mb-3 rounded bg-sawo/10 px-3 py-2 text-sm text-sawo-darker dark:bg-sawo/15 dark:text-sawo-light">
                {kbMessage}
              </p>
            )}
            {kbError && (
              <p className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">
                {kbError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleExportKnowledgeBase}
                disabled={kbExporting}
                className="rounded border border-slate-300 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/15"
              >
                {kbExporting ? "Exporting..." : "Export Knowledge Base"}
              </button>
              <label
                className={`cursor-pointer rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 ${
                  kbImporting ? "cursor-not-allowed opacity-50" : ""
                }`}
              >
                {kbImporting ? "Importing..." : "Import Knowledge Base"}
                <input
                  type="file"
                  accept=".xlsx"
                  onChange={handleImportKnowledgeBase}
                  disabled={kbImporting}
                  className="hidden"
                />
              </label>
            </div>
          </div>

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
              {editingKey ? (
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder="Paste your OpenRouter API key"
                    autoComplete="off"
                    autoFocus={!!settings.openrouter_api_key}
                    className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
                  />
                  {settings.openrouter_api_key && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingKey(false);
                        setApiKeyInput("");
                      }}
                      className="shrink-0 rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-white/15 dark:text-slate-300 dark:hover:bg-white/5"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2 rounded border border-slate-300 bg-slate-50 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5">
                  <span className="select-none font-mono tracking-widest text-slate-500 dark:text-slate-400">
                    {OPENROUTER_KEY_MASK}
                  </span>
                  <button
                    type="button"
                    onClick={() => setEditingKey(true)}
                    className="shrink-0 text-xs font-medium text-sawo-dark hover:underline dark:text-sawo-light"
                  >
                    Change key
                  </button>
                </div>
              )}
              <p className="text-xs text-slate-400 dark:text-slate-500">
                {settings.openrouter_api_key
                  ? "A key is saved (shown masked above). Click \"Change key\" to replace it."
                  : "No key saved yet — paste one to enable the AI engine."}
              </p>
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

          <Link
            href="/admin/analytics"
            className="mt-8 flex max-w-xl items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm transition-colors hover:border-sawo/40 dark:border-white/10 dark:bg-night-surface dark:hover:border-sawo-light/50"
          >
            <span>
              <span className="block font-medium text-slate-800 dark:text-slate-100">AI usage &amp; cost analytics</span>
              <span className="text-slate-500 dark:text-slate-400">
                Per-model spend, request counts, and daily breakdowns live on the Analytics page.
              </span>
            </span>
            <span className="shrink-0 font-medium text-sawo-dark dark:text-sawo-light">View Analytics →</span>
          </Link>
        </>
      )}
    </div>
  );
}
