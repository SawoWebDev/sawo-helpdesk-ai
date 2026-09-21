"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/useCurrentUser";
import Pagination from "@/components/admin/Pagination";

interface KnowledgeEntry {
  id: number;
  title: string;
  content: string;
  memory_enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

interface SettingsOut {
  general_knowledge_enabled: boolean;
  [key: string]: unknown;
}

function Switch({ checked, onChange, disabled }: { checked: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      disabled={disabled}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
        checked ? "bg-sawo dark:bg-sawo-dark" : "bg-slate-300 dark:bg-white/20"
      }`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-[22px]" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export default function GeneralKnowledgePage() {
  const { user } = useCurrentUser();
  const isAdmin = user?.role === "admin";

  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [togglingSource, setTogglingSource] = useState(false);

  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");

  const [error, setError] = useState<string | null>(null);

  async function loadSettings() {
    const data = await apiGet<SettingsOut>("/api/settings");
    setEnabled(data.general_knowledge_enabled);
  }

  async function loadEntries() {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      source_type: "manual",
    });
    const data = await apiGet<Paginated<KnowledgeEntry>>(`/api/vault?${params.toString()}`);
    setEntries(data.items);
    setTotal(data.total);
  }

  useEffect(() => {
    // /api/settings is admin-only (it also carries API keys) — an agent
    // calling it would just get a 403, so skip the request entirely and
    // leave the switch showing its disabled/unknown state for them.
    if (isAdmin) loadSettings().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  useEffect(() => {
    loadEntries().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  async function toggleSource() {
    if (enabled === null) return;
    const next = !enabled;
    setTogglingSource(true);
    setError(null);
    try {
      await apiPost("/api/settings", { general_knowledge_enabled: next });
      setEnabled(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update setting");
    } finally {
      setTogglingSource(false);
    }
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiPost("/api/vault", { title: title.trim(), content: content.trim() });
      setTitle("");
      setContent("");
      setPage(1);
      await loadEntries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add entry");
    } finally {
      setSubmitting(false);
    }
  }

  function startEdit(entry: KnowledgeEntry) {
    setEditingId(entry.id);
    setEditTitle(entry.title);
    setEditContent(entry.content);
  }

  async function saveEdit(id: number) {
    if (!editTitle.trim() || !editContent.trim()) return;
    setError(null);
    try {
      await apiPut(`/api/vault/${id}`, { title: editTitle.trim(), content: editContent.trim() });
      setEditingId(null);
      await loadEntries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save changes");
    }
  }

  async function toggleEntryActive(entry: KnowledgeEntry) {
    setError(null);
    try {
      await apiPut(`/api/vault/${entry.id}`, { memory_enabled: !entry.memory_enabled });
      await loadEntries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update entry");
    }
  }

  async function handleDelete(entry: KnowledgeEntry) {
    if (!confirm(`Delete "${entry.title}"?`)) return;
    setError(null);
    try {
      await apiDelete(`/api/vault/${entry.id}`);
      await loadEntries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete entry");
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800 dark:text-slate-100">General Knowledge</h1>
      </div>

      {error && (
        <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">
          {error}
        </p>
      )}

      <div className="mb-6 flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface">
        <div>
          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">Include General Knowledge as a source</p>
          <p className="text-xs text-slate-400 dark:text-slate-500">
            {isAdmin
              ? "When on, the chatbot can answer using both FAQs and the general SAWO info below. When off, it only answers from FAQs."
              : "Only admins can change this. When on, the chatbot can answer using both FAQs and the general SAWO info below."}
          </p>
        </div>
        <Switch
          checked={enabled ?? false}
          onChange={toggleSource}
          disabled={!isAdmin || enabled === null || togglingSource}
        />
      </div>

      <form
        onSubmit={handleAdd}
        className="mb-6 flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface"
      >
        <p className="text-sm font-medium text-slate-800 dark:text-slate-100">Add general info</p>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title, e.g. Company overview"
          className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste basic SAWO info here (about the company, products, locations, support channels, etc.)"
          rows={5}
          className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
        />
        <div>
          <button
            type="submit"
            disabled={submitting || !title.trim() || !content.trim()}
            className="rounded bg-sawo px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sawo-dark disabled:opacity-50 dark:bg-sawo-dark dark:hover:bg-sawo-darker"
          >
            {submitting ? "Adding..." : "Add"}
          </button>
        </div>
      </form>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500 dark:bg-white/5 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">Title</th>
              <th className="px-4 py-2">Content</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-t border-slate-100 align-top dark:border-white/10">
                {editingId === entry.id ? (
                  <td colSpan={4} className="px-4 py-3">
                    <div className="flex flex-col gap-2">
                      <input
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
                      />
                      <textarea
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        rows={4}
                        className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
                      />
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => saveEdit(entry.id)}
                          className="rounded bg-sawo px-3 py-1 text-sm font-medium text-white hover:bg-sawo-dark dark:bg-sawo-dark dark:hover:bg-sawo-darker"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="rounded border border-slate-300 px-3 py-1 text-sm dark:border-white/15 dark:text-slate-300"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </td>
                ) : (
                  <>
                    <td className="max-w-[12rem] truncate px-4 py-2 font-medium text-slate-800 dark:text-slate-100" title={entry.title}>
                      {entry.title}
                    </td>
                    <td className="max-w-sm truncate px-4 py-2 text-slate-500 dark:text-slate-400" title={entry.content}>
                      {entry.content}
                    </td>
                    <td className="px-4 py-2">
                      <button
                        type="button"
                        onClick={() => toggleEntryActive(entry)}
                        className={`rounded px-2 py-0.5 text-xs font-medium ${
                          entry.memory_enabled
                            ? "bg-green-50 text-green-700 hover:bg-green-100 dark:bg-green-500/15 dark:text-green-300 dark:hover:bg-green-500/25"
                            : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-400 dark:hover:bg-white/15"
                        }`}
                      >
                        {entry.memory_enabled ? "Active" : "Inactive"}
                      </button>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => startEdit(entry)}
                        className="mr-3 text-sawo-dark dark:text-sawo-light"
                      >
                        Edit
                      </button>
                      <button type="button" onClick={() => handleDelete(entry)} className="text-red-600 dark:text-red-400">
                        Delete
                      </button>
                    </td>
                  </>
                )}
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-slate-400 dark:text-slate-500">
                  No general knowledge entries yet. Add some basic SAWO info above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
      </div>
    </div>
  );
}
