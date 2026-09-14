"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiDelete, apiGet, apiPut, downloadFile, getToken, ApiError } from "@/lib/api";
import CategorySelect, { CategoryOption } from "@/components/admin/CategorySelect";
import Pagination from "@/components/admin/Pagination";

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

export default function FAQListPage() {
  const [faqs, setFaqs] = useState<FAQ[]>([]);
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<"" | "published" | "draft">("");
  const [importSummary, setImportSummary] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
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
    await apiPut(`/api/faqs/${faq.id}`, { status: nextStatus });
    await load();
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
      const query = params.toString();
      await downloadFile(`/api/faqs/export${query ? `?${query}` : ""}`, "faq_export.xlsx");
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Failed to export FAQs");
    }
  }

  function categoryName(id: number | null) {
    if (id === null) return "—";
    return categories.find((c) => c.id === id)?.name ?? "—";
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">FAQ Knowledge Base</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleDownloadTemplate}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            Download Template
          </button>
          <button
            type="button"
            onClick={handleExport}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            Export Excel
          </button>
          <label className="cursor-pointer rounded border border-slate-300 px-3 py-2 text-sm">
            Import Excel
            <input type="file" accept=".xlsx" onChange={handleImport} className="hidden" />
          </label>
          <Link href="/admin/faqs/new" className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white">
            New FAQ
          </Link>
        </div>
      </div>

      {importSummary && (
        <p className="mb-4 rounded bg-blue-50 px-3 py-2 text-sm text-blue-800">{importSummary}</p>
      )}
      {downloadError && (
        <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{downloadError}</p>
      )}

      <div className="mb-4 flex gap-2">
        <input
          value={search}
          onChange={(e) => {
            setPage(1);
            setSearch(e.target.value);
          }}
          placeholder="Search questions/answers..."
          className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm"
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
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="published">Published</option>
          <option value="draft">Draft</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
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
              <tr key={faq.id} className="border-t border-slate-100">
                <td className="max-w-md truncate px-4 py-2">{faq.question}</td>
                <td className="px-4 py-2 text-slate-500">{categoryName(faq.category_id)}</td>
                <td className="px-4 py-2 text-slate-500" title={faq.source_label ?? undefined}>
                  {faq.source}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      faq.status === "published" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {faq.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => handleToggleStatus(faq)} className="mr-3 text-blue-600">
                    {faq.status === "published" ? "Unpublish" : "Publish"}
                  </button>
                  <Link href={`/admin/faqs/${faq.id}`} className="mr-3 text-blue-600">
                    Edit
                  </Link>
                  <button onClick={() => handleDelete(faq.id)} className="text-red-600">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {faqs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                  No FAQ entries found.
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
