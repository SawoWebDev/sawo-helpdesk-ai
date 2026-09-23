"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { FileText, LayoutGrid, List as ListIcon, Trash2, X } from "lucide-react";
import { apiDelete, apiGet, apiPost, apiPut, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/useCurrentUser";
import Pagination from "@/components/admin/Pagination";
import PageHeader from "@/components/admin/PageHeader";

interface KnowledgeEntry {
  id: number;
  title: string;
  content: string;
  memory_enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface ChatbotKbEntry {
  id: number;
  title: string;
  content: string;
  category_path: string;
  memory_enabled: boolean;
  source_url: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

interface SettingsOut {
  general_knowledge_enabled: boolean;
  chatbot_kb_enabled: boolean;
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
        className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
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

  const [chatbotKbEnabled, setChatbotKbEnabled] = useState<boolean | null>(null);
  const [togglingChatbotKb, setTogglingChatbotKb] = useState(false);

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

  const [chatbotKbEntries, setChatbotKbEntries] = useState<ChatbotKbEntry[] | null>(null);
  const [chatbotKbQuery, setChatbotKbQuery] = useState("");
  const [chatbotKbView, setChatbotKbView] = useState<"list" | "grid">("list");

  const [editingChatbotKbEntry, setEditingChatbotKbEntry] = useState<ChatbotKbEntry | null>(null);
  const [editChatbotKbTitle, setEditChatbotKbTitle] = useState("");
  const [editChatbotKbContent, setEditChatbotKbContent] = useState("");
  const [editChatbotKbSourceUrl, setEditChatbotKbSourceUrl] = useState("");
  const [savingChatbotKbEdit, setSavingChatbotKbEdit] = useState(false);

  async function loadSettings() {
    const data = await apiGet<SettingsOut>("/api/settings");
    setEnabled(data.general_knowledge_enabled);
    setChatbotKbEnabled(data.chatbot_kb_enabled);
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

  async function loadChatbotKb() {
    const data = await apiGet<ChatbotKbEntry[]>("/api/vault/chatbot-kb");
    setChatbotKbEntries(data);
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

  useEffect(() => {
    loadChatbotKb().catch(() => {});
  }, []);

  // Drop the shared "SAWO Chatbot KB" root from the label — every entry in
  // this list already lives inside this section, so repeating it on every
  // row would just be noise. What's left ("General", "Products > ...") is
  // shown as a small tag, same idea as the sawochatbot KB's own section list.
  function chatbotKbCategoryLabel(entry: ChatbotKbEntry) {
    return entry.category_path.replace(/^SAWO Chatbot KB\s*>?\s*/, "") || "General";
  }

  const filteredChatbotKbEntries = useMemo(() => {
    if (!chatbotKbEntries) return [];
    const query = chatbotKbQuery.trim().toLowerCase();
    const filtered = query
      ? chatbotKbEntries.filter(
          (e) => e.title.toLowerCase().includes(query) || e.content.toLowerCase().includes(query)
        )
      : chatbotKbEntries;
    return [...filtered].sort(
      (a, b) => a.category_path.localeCompare(b.category_path) || a.title.localeCompare(b.title)
    );
  }, [chatbotKbEntries, chatbotKbQuery]);

  function openChatbotKbEditor(entry: ChatbotKbEntry) {
    setEditingChatbotKbEntry(entry);
    setEditChatbotKbTitle(entry.title);
    setEditChatbotKbContent(entry.content);
    setEditChatbotKbSourceUrl(entry.source_url ?? "");
  }

  function closeChatbotKbEditor() {
    setEditingChatbotKbEntry(null);
  }

  async function saveChatbotKbEdit() {
    if (!editingChatbotKbEntry || !editChatbotKbTitle.trim() || !editChatbotKbContent.trim()) return;
    setSavingChatbotKbEdit(true);
    setError(null);
    try {
      await apiPut(`/api/vault/${editingChatbotKbEntry.id}`, {
        title: editChatbotKbTitle.trim(),
        content: editChatbotKbContent.trim(),
        source_url: editChatbotKbSourceUrl.trim() || null,
      });
      setEditingChatbotKbEntry(null);
      await loadChatbotKb();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save changes");
    } finally {
      setSavingChatbotKbEdit(false);
    }
  }

  async function toggleChatbotKbEntryActive(entry: ChatbotKbEntry) {
    setError(null);
    try {
      await apiPut(`/api/vault/${entry.id}`, { memory_enabled: !entry.memory_enabled });
      await loadChatbotKb();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update entry");
    }
  }

  async function deleteChatbotKbEntry(entry: ChatbotKbEntry) {
    if (!confirm(`Delete "${entry.title}"?`)) return;
    setError(null);
    try {
      await apiDelete(`/api/vault/${entry.id}`);
      await loadChatbotKb();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete entry");
    }
  }

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

  async function toggleChatbotKb() {
    if (chatbotKbEnabled === null) return;
    const next = !chatbotKbEnabled;
    setTogglingChatbotKb(true);
    setError(null);
    try {
      await apiPost("/api/settings", { chatbot_kb_enabled: next });
      setChatbotKbEnabled(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update setting");
    } finally {
      setTogglingChatbotKb(false);
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
      <PageHeader
        icon="fa-solid fa-brain"
        title="Knowledge Base"
        description="Control what the chatbot can draw on when answering."
        actions={
          <div className="flex flex-wrap items-center gap-5">
            <label className="flex items-center gap-2 text-xs font-medium text-white/85">
              General Knowledge
              <Switch
                checked={enabled ?? false}
                onChange={toggleSource}
                disabled={!isAdmin || enabled === null || togglingSource}
              />
            </label>
            <label className="flex items-center gap-2 text-xs font-medium text-white/85">
              SAWO Chatbot import
              <Switch
                checked={chatbotKbEnabled ?? false}
                onChange={toggleChatbotKb}
                disabled={!isAdmin || chatbotKbEnabled === null || togglingChatbotKb}
              />
            </label>
          </div>
        }
      />

      {error && (
        <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">
          {error}
        </p>
      )}

      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">SAWO Chatbot Knowledge Base</h2>
            <span className="rounded-full bg-sawo/10 px-2 py-0.5 text-xs font-semibold text-sawo-dark dark:bg-sawo/20 dark:text-sawo-light">
              {chatbotKbEntries?.length ?? 0}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <input
              value={chatbotKbQuery}
              onChange={(e) => setChatbotKbQuery(e.target.value)}
              placeholder="Search sections..."
              className="w-48 rounded border border-slate-300 px-3 py-1.5 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
            />
            <div className="flex overflow-hidden rounded-md border border-slate-300 text-xs font-medium dark:border-white/15">
              <button
                type="button"
                onClick={() => setChatbotKbView("list")}
                className={`flex items-center gap-1 px-3 py-1.5 ${
                  chatbotKbView === "list"
                    ? "bg-sawo text-white"
                    : "text-slate-500 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-white/5"
                }`}
              >
                <ListIcon className="h-3.5 w-3.5" /> List
              </button>
              <button
                type="button"
                onClick={() => setChatbotKbView("grid")}
                className={`flex items-center gap-1 px-3 py-1.5 ${
                  chatbotKbView === "grid"
                    ? "bg-sawo text-white"
                    : "text-slate-500 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-white/5"
                }`}
              >
                <LayoutGrid className="h-3.5 w-3.5" /> Grid
              </button>
            </div>
          </div>
        </div>
        <p className="mb-3 text-xs text-slate-400 dark:text-slate-500">
          Imported from the SAWO chatbot&apos;s own knowledge base — read-only, kept separate from crawled Library content.
        </p>

        {chatbotKbEntries === null && (
            <p className="py-4 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
          {chatbotKbEntries !== null && chatbotKbEntries.length === 0 && (
            <p className="py-4 text-center text-sm text-slate-400 dark:text-slate-500">
              Nothing imported yet. Upload the sawochatbot export via Settings &gt; Knowledge Base import.
            </p>
          )}
          {filteredChatbotKbEntries.length === 0 && chatbotKbEntries !== null && chatbotKbEntries.length > 0 && (
            <p className="py-4 text-center text-sm text-slate-400 dark:text-slate-500">
              No entries match &quot;{chatbotKbQuery}&quot;.
            </p>
          )}

          {chatbotKbView === "list" ? (
            <div className="flex flex-col divide-y divide-slate-100 dark:divide-white/10">
              {filteredChatbotKbEntries.map((entry) => {
                return (
                  <div key={entry.id} className="flex w-full items-start gap-3 py-3">
                    <button
                      type="button"
                      onClick={() => openChatbotKbEditor(entry)}
                      className="flex min-w-0 flex-1 items-start gap-3 text-left"
                    >
                      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-sawo/10 text-sawo-dark dark:bg-sawo/15 dark:text-sawo-light">
                        <FileText className="h-4 w-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">{entry.title}</span>
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-white/10 dark:text-slate-400">
                            {chatbotKbCategoryLabel(entry)}
                          </span>
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-slate-400 dark:text-slate-500">{entry.content}</span>
                      </span>
                    </button>
                    <span className="flex shrink-0 items-center gap-2 pl-2">
                      <button
                        type="button"
                        onClick={() => toggleChatbotKbEntryActive(entry)}
                        className={`rounded px-2 py-0.5 text-xs font-medium ${
                          entry.memory_enabled
                            ? "bg-green-50 text-green-700 hover:bg-green-100 dark:bg-green-500/15 dark:text-green-300 dark:hover:bg-green-500/25"
                            : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-400 dark:hover:bg-white/15"
                        }`}
                      >
                        {entry.memory_enabled ? "Active" : "Inactive"}
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteChatbotKbEntry(entry)}
                        className="text-slate-400 hover:text-red-600 dark:text-slate-500 dark:hover:text-red-400"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {filteredChatbotKbEntries.map((entry) => {
                return (
                  <div key={entry.id} className="rounded-lg border border-slate-100 p-3 dark:border-white/10">
                    <button
                      type="button"
                      onClick={() => openChatbotKbEditor(entry)}
                      className="flex w-full items-start gap-2 text-left"
                    >
                      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-sawo/10 text-sawo-dark dark:bg-sawo/15 dark:text-sawo-light">
                        <FileText className="h-3.5 w-3.5" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-slate-800 dark:text-slate-100">{entry.title}</span>
                        <span className="mt-0.5 inline-block w-fit rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-white/10 dark:text-slate-400">
                          {chatbotKbCategoryLabel(entry)}
                        </span>
                      </span>
                    </button>
                    <p className="mt-2 line-clamp-3 text-xs text-slate-400 dark:text-slate-500">{entry.content}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => toggleChatbotKbEntryActive(entry)}
                        className={`rounded px-2 py-0.5 text-xs font-medium ${
                          entry.memory_enabled
                            ? "bg-green-50 text-green-700 hover:bg-green-100 dark:bg-green-500/15 dark:text-green-300 dark:hover:bg-green-500/25"
                            : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-400 dark:hover:bg-white/15"
                        }`}
                      >
                        {entry.memory_enabled ? "Active" : "Inactive"}
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteChatbotKbEntry(entry)}
                        className="ml-auto text-slate-400 hover:text-red-600 dark:text-slate-500 dark:hover:text-red-400"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
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

      {editingChatbotKbEntry && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={closeChatbotKbEditor}
        >
          <div
            className="flex max-h-[85vh] w-full max-w-xl flex-col rounded-lg bg-white shadow-xl dark:bg-night-surface"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-white/10">
              <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Edit Section</h2>
              <button
                type="button"
                onClick={closeChatbotKbEditor}
                className="text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4">
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                Section Name
              </label>
              <input
                value={editChatbotKbTitle}
                onChange={(e) => setEditChatbotKbTitle(e.target.value)}
                className="mb-4 w-full rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
              />

              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                Content
              </label>
              <textarea
                value={editChatbotKbContent}
                onChange={(e) => setEditChatbotKbContent(e.target.value)}
                rows={16}
                className="w-full rounded border border-slate-300 px-3 py-2 font-mono text-xs leading-relaxed dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
              />

              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                Source URL
              </label>
              <input
                value={editChatbotKbSourceUrl}
                onChange={(e) => setEditChatbotKbSourceUrl(e.target.value)}
                placeholder="https://www.sawo.com/..."
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
              />
              {editChatbotKbSourceUrl && (
                <a
                  href={editChatbotKbSourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-xs text-sawo-dark underline underline-offset-2 dark:text-sawo-light"
                >
                  Open link ↗
                </a>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-white/10">
              <button
                type="button"
                onClick={closeChatbotKbEditor}
                className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-white/15 dark:text-slate-300 dark:hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveChatbotKbEdit}
                disabled={savingChatbotKbEdit || !editChatbotKbTitle.trim() || !editChatbotKbContent.trim()}
                className="rounded bg-sawo px-4 py-2 text-sm font-medium text-white hover:bg-sawo-dark disabled:opacity-50 dark:bg-sawo-dark dark:hover:bg-sawo-darker"
              >
                {savingChatbotKbEdit ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
