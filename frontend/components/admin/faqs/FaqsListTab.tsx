"use client";

import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPut, downloadFile, getToken, ApiError } from "@/lib/api";
import CategorySelect, { CategoryOption } from "@/components/admin/CategorySelect";
import Pagination from "@/components/admin/Pagination";
import { pick, sourceColor, sourceLabel } from "@/components/admin/analytics/colors";
import { useIsDark } from "@/lib/useIsDark";
import FAQModal from "./FAQModal";

interface FAQ {
  id: number;
  question: string;
  answer: string;
  category_id: number | null;
  source: string;
  source_label: string | null;
  status: "published" | "draft";
  updated_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export default function FaqsListTab() {
  const isDark = useIsDark();
  const [faqs, setFaqs] = useState<FAQ[]>([]);
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<"" | "published" | "draft">("");
  const [importSummary, setImportSummary] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [modal, setModal] = useState<{ faqId?: number } | null>(null);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportIncludeDrafts, setExportIncludeDrafts] = useState(true);
  const pageSize = 20;

  async function load() {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (search) params.set("search", search);
    if (categoryId !== null) params.set("category_id", String(categoryId));
    if (statusFilter) params.set("status", statusFilter);
    const data = await apiGet<Paginated<FAQ>>(`/api/faqs?${params.toString()}`);
    setFaqs(data.items);
    setTotal(data.total);
  }

  useEffect(() => {
    apiGet<CategoryOption[]>("/api/categories").then(setCategories);
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, search, categoryId, statusFilter]);

  async function handleDelete(id: number) {
    if (!confirm("Delete this FAQ entry?")) return;
    await apiDelete(`/api/faqs/${id}`);
    await load();
  }

  async function handleToggleStatus(faq: FAQ) {
    const nextStatus = faq.status === "published" ? "draft" : "published";
    // A chat_auto draft is unverified AI output -- it reads as a complete,
    // well-formatted answer, which is exactly what makes a wrong one easy to
    // approve on a skim (an auto-saved answer once cited the wrong product
    // page and got published this way). Publishing is the one-click step
    // that turns it into trusted content the chatbot cites as fact, so it
    // gets a confirmation the other, human-authored sources do not need.
    if (nextStatus === "published" && faq.source === "chat_auto") {
      const ok = confirm(
        "This answer was auto-saved from a chat reply and has not been reviewed. " +
          "Before publishing, check every fact and link against the source page " +
          "it was drawn from -- a wrong answer here gets cited by the chatbot as " +
          "verified fact.\n\nPublish anyway?"
      );
      if (!ok) return;
    }
    await apiPut(`/api/faqs/${faq.id}`, { status: nextStatus });
    await load();
  }

  function handleModalSaved() {
    setModal(null);
    load();
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    const token = getToken();
    const res = await fetch("/api/faqs/import", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: formData,
    });
    const data = await res.json();
    setImportSummary(
      `Created: ${data.created}, Skipped: ${data.skipped}, Failed: ${data.failed}` +
        (data.errors?.length ? ` — ${data.errors.length} row error(s), see console` : "")
    );
    if (data.errors?.length) console.table(data.errors);
    e.target.value = "";
    await load();
  }

  async function handleDownloadTemplate() {
    setDownloadError(null);
    try {
      await downloadFile("/api/faqs/template", "faq_import_template.xlsx");
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Failed to download template");
    }
  }

  async function handleExport() {
    setDownloadError(null);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (categoryId !== null) params.set("category_id", String(categoryId));
      params.set("include_drafts", String(exportIncludeDrafts));
      await downloadFile(`/api/faqs/export?${params.toString()}`, "faq_export.xlsx");
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Failed to export FAQs");
    } finally {
      setExportModalOpen(false);
    }
  }

  function categoryName(id: number | null) {
    if (id === null) return "—";
    return categories.find((c) => c.id === id)?.name ?? "—";
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleDownloadTemplate}
            className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15"
          >
            Download Template
          </button>
          <button
            type="button"
            onClick={() => setExportModalOpen(true)}
            className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15"
          >
            Export Excel
          </button>
          <label className="cursor-pointer rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15">
            Import Excel
            <input type="file" accept=".xlsx" onChange={handleImport} className="hidden" />
          </label>
        </div>
        <button
          type="button"
          onClick={() => setModal({})}
          className="rounded bg-sawo px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sawo-dark dark:bg-sawo-dark dark:hover:bg-sawo-darker"
        >
          New FAQ
        </button>
      </div>

      {importSummary && (
        <p className="mb-4 rounded bg-sawo/10 px-3 py-2 text-sm text-sawo-darker dark:bg-sawo/15 dark:text-sawo-light">{importSummary}</p>
      )}
      {downloadError && (
        <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">{downloadError}</p>
      )}

      <div className="mb-4 flex gap-2">
        <input
          value={search}
          onChange={(e) => {
            setPage(1);
            setSearch(e.target.value);
          }}
          placeholder="Search questions/answers..."
          className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
        />
        <CategorySelect
          categories={categories}
          value={categoryId}
          onChange={(id) => {
            setPage(1);
            setCategoryId(id);
          }}
        />
        <select
          value={statusFilter}
          onChange={(e) => {
            setPage(1);
            setStatusFilter(e.target.value as "" | "published" | "draft");
          }}
          className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
        >
          {/* The closed control's dark: classes only paint the collapsed box —
              the native options popup ignores them and defaults to a white
              background, so the light dark:text color above was unreadable
              against it. Styling the <option>s directly is what Chromium/Edge
              actually use to paint that popup (same fix as Chat Logs' rating
              filter). */}
          <option value="" className="dark:bg-night-surface dark:text-slate-100">All statuses</option>
          <option value="published" className="dark:bg-night-surface dark:text-slate-100">Published</option>
          <option value="draft" className="dark:bg-night-surface dark:text-slate-100">Draft</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500 dark:bg-white/5 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">Question</th>
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2">Source</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {faqs.map((faq) => (
              <tr key={faq.id} className="border-t border-slate-100 dark:border-white/10">
                <td className="max-w-md truncate px-4 py-2">{faq.question}</td>
                <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{categoryName(faq.category_id)}</td>
                <td className="px-4 py-2" title={faq.source_label ?? undefined}>
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: pick(sourceColor(faq.source), isDark) }}
                    />
                    {sourceLabel(faq.source)}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      faq.status === "published"
                        ? "bg-green-50 text-green-700 dark:bg-green-500/15 dark:text-green-300"
                        : "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
                    }`}
                  >
                    {faq.status}
                  </span>
                  {faq.status === "draft" && faq.source === "chat_auto" && (
                    <span
                      title="AI-generated from a chat reply, not yet checked by a person -- verify it against the source before publishing"
                      className="ml-1.5 rounded px-2 py-0.5 text-xs font-medium bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"
                    >
                      Needs review
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => handleToggleStatus(faq)} className="mr-3 text-sawo-dark dark:text-sawo-light">
                    {faq.status === "published" ? "Unpublish" : "Publish"}
                  </button>
                  <button onClick={() => setModal({ faqId: faq.id })} className="mr-3 text-sawo-dark dark:text-sawo-light">
                    Edit
                  </button>
                  <button onClick={() => handleDelete(faq.id)} className="text-red-600 dark:text-red-400">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {faqs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-400 dark:text-slate-500">
                  No FAQ entries found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
      </div>

      {modal && <FAQModal faqId={modal.faqId} onClose={() => setModal(null)} onSaved={handleModalSaved} />}

      {exportModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setExportModalOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-xl bg-white shadow-2xl dark:bg-night-surface"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-slate-200 px-5 py-4 dark:border-white/10">
              <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Export FAQs</h2>
            </div>
            <div className="flex flex-col gap-4 p-5">
              <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <input
                  type="checkbox"
                  checked={exportIncludeDrafts}
                  onChange={(e) => setExportIncludeDrafts(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 dark:border-white/15"
                />
                Include draft FAQs
              </label>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setExportModalOpen(false)}
                  className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-white/15 dark:text-slate-300 dark:hover:bg-white/5"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleExport}
                  className="rounded bg-sawo px-3 py-2 text-sm font-medium text-white hover:bg-sawo-dark dark:bg-sawo-dark dark:hover:bg-sawo-darker"
                >
                  Download
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
