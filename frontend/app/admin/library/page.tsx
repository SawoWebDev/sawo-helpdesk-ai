"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, getToken, ApiError } from "@/lib/api";
import CategorySelect, { CategoryOption } from "@/components/admin/CategorySelect";
import Pagination from "@/components/admin/Pagination";

interface LibrarySource {
  id: number;
  source_type: "file" | "url";
  origin_url: string | null;
  original_filename: string | null;
  category_id: number | null;
  status: "pending" | "processing" | "indexed" | "failed";
  error_message: string | null;
  extracted_char_count: number | null;
  chunk_count: number;
  auto_generate_faqs: boolean;
  faq_generation_status: string | null;
  generated_faq_count: number;
  created_at: string;
  processed_at: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

interface SearchResult {
  entry_id: number;
  title: string;
  excerpt: string;
  score: number;
  match_type: string;
  source_id: number | null;
  category_id: number | null;
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-slate-100 text-slate-600",
  processing: "bg-blue-50 text-blue-700",
  indexed: "bg-green-50 text-green-700",
  failed: "bg-red-50 text-red-700",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? "bg-slate-100 text-slate-600"}`}>
      {status}
    </span>
  );
}

// The backend wraps keyword matches in the excerpt with literal "**" markers
// (FTS5 snippet()). Render those as <strong> without ever passing document
// content through dangerouslySetInnerHTML, since excerpt text can come from
// an arbitrary crawled web page.
function HighlightedExcerpt({ text }: { text: string }) {
  const parts = text.split("**");
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <strong key={i}>{part}</strong> : <span key={i}>{part}</span>
      )}
    </>
  );
}

export default function LibraryPage() {
  const [activeTab, setActiveTab] = useState<"file" | "url">("file");
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [sources, setSources] = useState<LibrarySource[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [autoGenerateFaqs, setAutoGenerateFaqs] = useState(true);

  const [file, setFile] = useState<File | null>(null);
  const [crawlUrl, setCrawlUrl] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchAnswer, setSearchAnswer] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);

  async function loadCategories() {
    const data = await apiGet<CategoryOption[]>("/api/categories");
    setCategories(data);
  }

  async function loadSources() {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    const data = await apiGet<Paginated<LibrarySource>>(`/api/library/sources?${params.toString()}`);
    setSources(data.items);
    setTotal(data.total);
  }

  useEffect(() => {
    loadCategories();
  }, []);

  useEffect(() => {
    loadSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  // Any source still pending/processing gets polled so status updates
  // (Indexed, FAQ counts) show up without a manual refresh.
  useEffect(() => {
    const hasInFlight = sources.some((s) => s.status === "pending" || s.status === "processing");
    if (!hasInFlight) return;
    const interval = setInterval(loadSources, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sources]);

  function categoryName(id: number | null) {
    if (id === null) return "—";
    return categories.find((c) => c.id === id)?.name ?? "—";
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const params = new URLSearchParams({ auto_generate_faqs: String(autoGenerateFaqs) });
      if (newCategoryName.trim()) params.set("new_category_name", newCategoryName.trim());
      else if (categoryId !== null) params.set("category_id", String(categoryId));

      const token = getToken();
      const res = await fetch(`/api/library/upload?${params.toString()}`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new ApiError(res.status, data.detail || "Upload failed");
      }
      setMessage(`Uploaded "${file.name}" — processing in the background.`);
      setFile(null);
      setNewCategoryName("");
      if (newCategoryName.trim()) await loadCategories();
      await loadSources();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to upload document");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCrawl(e: FormEvent) {
    e.preventDefault();
    if (!crawlUrl.trim()) return;
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      await apiPost("/api/library/crawl", {
        url: crawlUrl.trim(),
        category_id: newCategoryName.trim() ? null : categoryId,
        new_category_name: newCategoryName.trim() || null,
        auto_generate_faqs: autoGenerateFaqs,
      });
      setMessage(`Queued crawl for ${crawlUrl.trim()}`);
      setCrawlUrl("");
      setNewCategoryName("");
      if (newCategoryName.trim()) await loadCategories();
      await loadSources();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start crawl");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGenerateFaqs(source: LibrarySource) {
    setError(null);
    try {
      await apiPost(`/api/library/sources/${source.id}/generate-faqs`, {});
      setMessage(`Re-running FAQ generation for "${source.original_filename ?? source.origin_url}".`);
      await loadSources();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to trigger FAQ generation");
    }
  }

  async function handleDelete(source: LibrarySource) {
    if (!confirm("Delete this Library source and its indexed content? Generated FAQs are kept.")) return;
    await apiDelete(`/api/library/sources/${source.id}`);
    await loadSources();
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const data = await apiPost<{ answer: string | null; results: SearchResult[] }>("/api/library/search", {
        query: searchQuery.trim(),
      });
      setSearchAnswer(data.answer);
      setSearchResults(data.results);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Library</h1>
      </div>

      {error && <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {message && <p className="mb-4 rounded bg-blue-50 px-3 py-2 text-sm text-blue-800">{message}</p>}

      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-4 flex gap-2 border-b border-slate-200">
          <button
            type="button"
            onClick={() => setActiveTab("file")}
            className={`px-3 py-2 text-sm font-medium ${
              activeTab === "file" ? "border-b-2 border-blue-600 text-blue-700" : "text-slate-500"
            }`}
          >
            File Upload
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("url")}
            className={`px-3 py-2 text-sm font-medium ${
              activeTab === "url" ? "border-b-2 border-blue-600 text-blue-700" : "text-slate-500"
            }`}
          >
            Web Crawler
          </button>
        </div>

        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">Category</label>
            <CategorySelect
              categories={categories}
              value={categoryId}
              onChange={setCategoryId}
              allowEmpty
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">Or create new category</label>
            <input
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              placeholder="e.g. IT technical"
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={autoGenerateFaqs}
              onChange={(e) => setAutoGenerateFaqs(e.target.checked)}
            />
            Auto-generate FAQs
          </label>
        </div>

        {activeTab === "file" ? (
          <form onSubmit={handleUpload} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500">Document (.pdf, .docx, .xlsx)</label>
              <input
                type="file"
                accept=".pdf,.docx,.xlsx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={submitting || !file}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {submitting ? "Uploading..." : "Upload & Index"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleCrawl} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500">URL</label>
              <input
                value={crawlUrl}
                onChange={(e) => setCrawlUrl(e.target.value)}
                placeholder="https://example.com/docs"
                className="w-72 rounded border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={submitting || !crawlUrl.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {submitting ? "Queuing..." : "Crawl & Index"}
            </button>
          </form>
        )}
      </div>

      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Hybrid search across indexed Library content..."
            className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={searching}
            className="rounded border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {searching ? "Searching..." : "Search"}
          </button>
          {searchResults && (
            <button
              type="button"
              onClick={() => {
                setSearchAnswer(null);
                setSearchResults(null);
                setSearchQuery("");
              }}
              className="rounded border border-slate-300 px-3 py-2 text-sm text-slate-500"
            >
              Clear
            </button>
          )}
        </form>

        {searchResults && (
          <div className="mt-4 flex flex-col gap-4">
            {searchAnswer && (
              <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-blue-700">Answer</p>
                <p className="text-sm text-slate-800">{searchAnswer}</p>
              </div>
            )}
            {!searchAnswer && (
              <p className="text-sm text-slate-400">
                {searchResults.length === 0
                  ? "No matches found."
                  : "No confident answer could be generated from the indexed content — showing raw matches below."}
              </p>
            )}
            {searchResults.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Matched sources</p>
                {searchResults.map((r) => (
                  <div key={r.entry_id} className="rounded border border-slate-100 p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-800">{r.title}</span>
                      <span className="text-xs text-slate-400">
                        {r.match_type} · {(r.score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-slate-600">
                      <HighlightedExcerpt text={r.excerpt} />
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-2">Source</th>
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2">Chunks</th>
              <th className="px-4 py-2">Added</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">FAQs</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.id} className="border-t border-slate-100">
                <td className="max-w-xs truncate px-4 py-2" title={s.original_filename ?? s.origin_url ?? ""}>
                  {s.source_type === "file" ? s.original_filename : s.origin_url}
                </td>
                <td className="px-4 py-2 text-slate-500">{categoryName(s.category_id)}</td>
                <td className="px-4 py-2 text-slate-500">{s.chunk_count}</td>
                <td className="px-4 py-2 text-slate-500">{new Date(s.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={s.status} />
                  {s.status === "failed" && s.error_message && (
                    <p className="mt-1 max-w-xs truncate text-xs text-red-500" title={s.error_message}>
                      {s.error_message}
                    </p>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-500">
                  {s.faq_generation_status === "processing" ? "Generating..." : s.generated_faq_count}
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => handleGenerateFaqs(s)}
                    disabled={s.status !== "indexed"}
                    className="mr-3 text-blue-600 disabled:cursor-not-allowed disabled:text-slate-300"
                  >
                    Generate FAQs
                  </button>
                  <button onClick={() => handleDelete(s)} className="text-red-600">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {sources.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-slate-400">
                  No Library sources yet. Upload a document or crawl a URL above.
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
