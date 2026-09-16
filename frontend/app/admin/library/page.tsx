"use client";

import { Fragment, FormEvent, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut, getToken, ApiError } from "@/lib/api";
import CategorySelect, { CategoryOption } from "@/components/admin/CategorySelect";
import Pagination from "@/components/admin/Pagination";

// Above this many discovered URLs, rendering one checkbox row per URL would
// put hundreds of thousands of DOM nodes on the page and freeze the browser
// tab — so the itemized list is hidden and only the aggregate Select
// All/None control is shown instead.
const LARGE_DISCOVERY_THRESHOLD = 500;

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
  created_at: string;
  processed_at: string | null;
}

interface LibraryBatchSummary {
  job_id: number;
  source_count: number;
  indexed_count: number;
  failed_count: number;
  pending_count: number;
  category_id: number | null;
  created_at: string;
  origin_label: string;
}

interface LibraryRow {
  kind: "source" | "batch";
  source: LibrarySource | null;
  batch: LibraryBatchSummary | null;
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
  source_url: string | null;
}

interface AnswerSource {
  title: string;
  source_url: string | null;
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

function SourceRow({
  source: s,
  categoryName,
  onDelete,
  onRetry,
  retrying,
  indent,
}: {
  source: LibrarySource;
  categoryName: (id: number | null) => string;
  onDelete: (source: LibrarySource) => void;
  onRetry: (source: LibrarySource) => void;
  retrying: boolean;
  indent: boolean;
}) {
  return (
    <tr className="border-t border-slate-100">
      <td className={`max-w-xs truncate px-4 py-2 ${indent ? "pl-10" : ""}`} title={s.original_filename ?? s.origin_url ?? ""}>
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
      <td className="px-4 py-2 text-right">
        {s.status === "failed" && (
          <button
            onClick={() => onRetry(s)}
            disabled={retrying}
            className="mr-3 text-blue-600 disabled:cursor-not-allowed disabled:text-slate-300"
          >
            {retrying ? "Retrying..." : "Retry"}
          </button>
        )}
        <button onClick={() => onDelete(s)} className="text-red-600">
          Delete
        </button>
      </td>
    </tr>
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
  const [rows, setRows] = useState<LibraryRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [jobSources, setJobSources] = useState<LibrarySource[] | null>(null);
  const [jobSourcesTotal, setJobSourcesTotal] = useState(0);
  const [jobSourcesPage, setJobSourcesPage] = useState(1);
  const jobSourcesPageSize = 20;
  const [jobSourcesLoading, setJobSourcesLoading] = useState(false);
  const [jobSourcesFilter, setJobSourcesFilter] = useState<string | null>(null);

  const [renamingJobId, setRenamingJobId] = useState<number | null>(null);
  const [renameLabel, setRenameLabel] = useState("");

  const [retryingSourceId, setRetryingSourceId] = useState<number | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<number | null>(null);

  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [newCategoryName, setNewCategoryName] = useState("");

  const [file, setFile] = useState<File | null>(null);
  const [crawlUrl, setCrawlUrl] = useState("");

  const [discovering, setDiscovering] = useState(false);
  const [discoveredUrls, setDiscoveredUrls] = useState<string[] | null>(null);
  // How many of the discovered URLs can actually be queued in one crawl
  // batch (the max_sitemap_urls setting) — a cap on crawling, not on how
  // many pages the sitemap actually lists.
  const [maxCrawlUrls, setMaxCrawlUrls] = useState<number | null>(null);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchAnswer, setSearchAnswer] = useState<string | null>(null);
  const [searchAnswerSources, setSearchAnswerSources] = useState<AnswerSource[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchResultsPage, setSearchResultsPage] = useState(1);
  const searchResultsPageSize = 5;
  const [searching, setSearching] = useState(false);

  async function loadCategories() {
    const data = await apiGet<CategoryOption[]>("/api/categories");
    setCategories(data);
  }

  async function loadSources() {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    const data = await apiGet<Paginated<LibraryRow>>(`/api/library/sources?${params.toString()}`);
    setRows(data.items);
    setTotal(data.total);
    // If a batch row is expanded, its child statuses may have changed too.
    if (expandedJobId !== null) {
      await loadJobSources(expandedJobId, jobSourcesFilter, jobSourcesPage);
    }
  }

  async function loadJobSources(jobId: number, statusFilter: string | null, pageNum: number = 1) {
    setJobSourcesLoading(true);
    try {
      const params = new URLSearchParams({ page: String(pageNum), page_size: String(jobSourcesPageSize) });
      if (statusFilter) params.set("status", statusFilter);
      const data = await apiGet<Paginated<LibrarySource>>(`/api/library/jobs/${jobId}/sources?${params.toString()}`);
      setJobSources(data.items);
      setJobSourcesTotal(data.total);
      setJobSourcesPage(pageNum);
    } finally {
      setJobSourcesLoading(false);
    }
  }

  async function toggleJob(jobId: number) {
    if (expandedJobId === jobId && jobSourcesFilter === null) {
      setExpandedJobId(null);
      setJobSources(null);
      return;
    }
    setExpandedJobId(jobId);
    setJobSourcesFilter(null);
    setJobSources(null);
    await loadJobSources(jobId, null, 1);
  }

  // Clicking a specific status badge (e.g. "1 failed") narrows the expanded
  // list to just that status — with a batch that can have thousands of
  // pages, loading everything just to find the one that failed isn't
  // practical. Clicking the same badge again collapses it.
  async function filterJobSources(jobId: number, statusFilter: string) {
    if (expandedJobId === jobId && jobSourcesFilter === statusFilter) {
      setExpandedJobId(null);
      setJobSources(null);
      return;
    }
    setExpandedJobId(jobId);
    setJobSourcesFilter(statusFilter);
    setJobSources(null);
    await loadJobSources(jobId, statusFilter, 1);
  }

  useEffect(() => {
    loadCategories();
  }, []);

  useEffect(() => {
    loadSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  // Any source still pending/processing gets polled so status updates
  // (Indexed, FAQ counts) show up without a manual refresh. A batch row
  // counts as "in flight" via its own pending_count/failed_count-derived
  // indexed_count check (source_count not yet fully indexed+failed).
  useEffect(() => {
    const hasInFlight = rows.some((r) => {
      if (r.kind === "source") return r.source?.status === "pending" || r.source?.status === "processing";
      if (r.kind === "batch" && r.batch) return r.batch.pending_count > 0;
      return false;
    });
    if (!hasInFlight) return;
    const interval = setInterval(loadSources, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

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
      const params = new URLSearchParams();
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

  async function handleDiscoverSitemap() {
    if (!crawlUrl.trim()) return;
    setDiscovering(true);
    setError(null);
    setMessage(null);
    setDiscoveredUrls(null);
    setMaxCrawlUrls(null);
    try {
      const data = await apiPost<{ urls: string[]; max_crawl_urls: number }>(
        "/api/library/discover-sitemap",
        { url: crawlUrl.trim() }
      );
      setDiscoveredUrls(data.urls);
      setMaxCrawlUrls(data.max_crawl_urls);
      setSelectedUrls(new Set(data.urls));
      if (data.urls.length === 0) {
        setMessage("Sitemap found, but it listed no pages.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to discover sitemap");
    } finally {
      setDiscovering(false);
    }
  }

  function toggleUrlSelected(url: string) {
    setSelectedUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  function toggleAllUrls() {
    if (!discoveredUrls) return;
    setSelectedUrls((prev) => (prev.size === discoveredUrls.length ? new Set() : new Set(discoveredUrls)));
  }

  async function handleCrawlSelected() {
    const urls = Array.from(selectedUrls);
    if (urls.length === 0) return;
    if (maxCrawlUrls !== null && urls.length > maxCrawlUrls) {
      setError(
        `You can crawl at most ${maxCrawlUrls} pages per batch (Settings > General > Max Sitemap URLs). ` +
          `${urls.length} are selected — deselect ${urls.length - maxCrawlUrls} more.`
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const data = await apiPost<{ queued: number }>("/api/library/crawl-batch", {
        urls,
        category_id: newCategoryName.trim() ? null : categoryId,
        new_category_name: newCategoryName.trim() || null,
      });
      setMessage(`Queued ${data.queued} page(s) for crawling.`);
      setDiscoveredUrls(null);
      setMaxCrawlUrls(null);
      setSelectedUrls(new Set());
      setCrawlUrl("");
      setNewCategoryName("");
      if (newCategoryName.trim()) await loadCategories();
      await loadSources();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to queue batch crawl");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(source: LibrarySource) {
    if (!confirm("Delete this Library source and its indexed content?")) return;
    await apiDelete(`/api/library/sources/${source.id}`);
    if (expandedJobId !== null) await loadJobSources(expandedJobId, jobSourcesFilter, jobSourcesPage);
    await loadSources();
  }

  async function handleRenameBatch(batch: LibraryBatchSummary) {
    if (!renameLabel.trim()) return;
    await apiPut(`/api/library/jobs/${batch.job_id}`, { label: renameLabel.trim() });
    setRenamingJobId(null);
    await loadSources();
  }

  async function handleRetry(source: LibrarySource) {
    setRetryingSourceId(source.id);
    setError(null);
    try {
      await apiPost(`/api/library/sources/${source.id}/retry`, {});
      if (expandedJobId !== null) await loadJobSources(expandedJobId, jobSourcesFilter, jobSourcesPage);
      await loadSources();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to retry source");
    } finally {
      setRetryingSourceId(null);
    }
  }

  async function handleRetryBatch(batch: LibraryBatchSummary) {
    setRetryingJobId(batch.job_id);
    setError(null);
    try {
      await apiPost(`/api/library/jobs/${batch.job_id}/retry`, {});
      // The retried pages just moved from failed -> pending, so re-fetching
      // under a "failed" filter would now show nothing; switch to "all" so
      // the pages that were just queued are still visible.
      if (expandedJobId === batch.job_id) {
        setJobSourcesFilter(null);
        await loadJobSources(batch.job_id, null, 1);
      }
      await loadSources();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to retry batch");
    } finally {
      setRetryingJobId(null);
    }
  }

  async function handleDeleteBatch(batch: LibraryBatchSummary) {
    if (
      !confirm(`Delete all ${batch.source_count} pages from this crawl (${batch.origin_label}) and their indexed content?`)
    )
      return;
    await apiDelete(`/api/library/jobs/${batch.job_id}`);
    if (expandedJobId === batch.job_id) {
      setExpandedJobId(null);
      setJobSources(null);
    }
    await loadSources();
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const data = await apiPost<{
        answer: string | null;
        answer_sources: AnswerSource[];
        results: SearchResult[];
      }>("/api/library/search", {
        query: searchQuery.trim(),
      });
      setSearchAnswer(data.answer);
      setSearchAnswerSources(data.answer_sources ?? []);
      setSearchResults(data.results);
      setSearchResultsPage(1);
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
          <div>
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
                {submitting ? "Queuing..." : "Crawl This Page"}
              </button>
              <button
                type="button"
                onClick={handleDiscoverSitemap}
                disabled={discovering || !crawlUrl.trim()}
                className="rounded border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-50"
              >
                {discovering ? "Discovering..." : "Discover All Pages (sitemap)"}
              </button>
            </form>
            <p className="mt-2 text-xs text-slate-400">
              &quot;Crawl This Page&quot; indexes only the URL above. &quot;Discover All Pages&quot; reads the
              site&apos;s sitemap.xml to find every page it publishes, so you can index the whole site at once.
            </p>

            {discoveredUrls && discoveredUrls.length > 0 && (
              <div className="mt-4 rounded-lg border border-slate-200 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={selectedUrls.size === discoveredUrls.length}
                      onChange={toggleAllUrls}
                    />
                    {selectedUrls.size} of {discoveredUrls.length} pages selected
                  </label>
                  <button
                    type="button"
                    onClick={handleCrawlSelected}
                    disabled={
                      submitting ||
                      selectedUrls.size === 0 ||
                      (maxCrawlUrls !== null && selectedUrls.size > maxCrawlUrls)
                    }
                    className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    {submitting ? "Queuing..." : `Crawl ${selectedUrls.size} Selected`}
                  </button>
                </div>
                {maxCrawlUrls !== null && selectedUrls.size > maxCrawlUrls && (
                  <p className="mb-2 text-xs text-amber-600">
                    You can crawl at most {maxCrawlUrls.toLocaleString()} pages per batch (Settings &gt; General
                    &gt; Max Sitemap URLs) — deselect {(selectedUrls.size - maxCrawlUrls).toLocaleString()} more to
                    continue.
                  </p>
                )}
                {discoveredUrls.length > LARGE_DISCOVERY_THRESHOLD ? (
                  <p className="rounded border border-slate-100 px-3 py-2 text-xs text-slate-400">
                    The individual page list isn&apos;t shown for sites this large (
                    {discoveredUrls.length.toLocaleString()} pages) — rendering every row would freeze the
                    browser tab. Use the checkbox above to select all or none.
                  </p>
                ) : (
                  <div className="max-h-64 overflow-y-auto rounded border border-slate-100">
                    {discoveredUrls.map((url) => (
                      <label
                        key={url}
                        className="flex items-center gap-2 border-t border-slate-50 px-3 py-1.5 text-sm text-slate-600 first:border-t-0 hover:bg-slate-50"
                      >
                        <input
                          type="checkbox"
                          checked={selectedUrls.has(url)}
                          onChange={() => toggleUrlSelected(url)}
                        />
                        <span className="truncate">{url}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
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
                setSearchAnswerSources([]);
                setSearchResults(null);
                setSearchResultsPage(1);
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
                {searchAnswerSources.length > 0 && (
                  <div className="mt-3 border-t border-blue-100 pt-2">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wide text-blue-700">
                      Sourced from
                    </p>
                    <ul className="flex flex-col gap-0.5">
                      {searchAnswerSources.map((s, i) =>
                        s.source_url ? (
                          <li key={i}>
                            <a
                              href={s.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-600 hover:underline"
                            >
                              {s.title}
                            </a>
                          </li>
                        ) : (
                          <li key={i} className="text-xs text-slate-500">
                            {s.title}
                          </li>
                        )
                      )}
                    </ul>
                  </div>
                )}
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
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                  Matched sources ({searchResults.length})
                </p>
                {searchResults
                  .slice((searchResultsPage - 1) * searchResultsPageSize, searchResultsPage * searchResultsPageSize)
                  .map((r) => (
                    <div key={r.entry_id} className="rounded border border-slate-100 p-3">
                      <div className="flex items-center justify-between">
                        {r.source_url ? (
                          <a
                            href={r.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium text-blue-600 hover:underline"
                          >
                            {r.title}
                          </a>
                        ) : (
                          <span className="text-sm font-medium text-slate-800">{r.title}</span>
                        )}
                        <span className="text-xs text-slate-400">
                          {r.match_type} · {(r.score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-slate-600">
                        <HighlightedExcerpt text={r.excerpt} />
                      </p>
                    </div>
                  ))}
                {searchResults.length > searchResultsPageSize && (
                  <Pagination
                    page={searchResultsPage}
                    pageSize={searchResultsPageSize}
                    total={searchResults.length}
                    onPageChange={setSearchResultsPage}
                  />
                )}
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
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              if (row.kind === "source" && row.source) {
                const s = row.source;
                return (
                  <SourceRow
                    key={`source-${s.id}`}
                    source={s}
                    categoryName={categoryName}
                    onDelete={handleDelete}
                    onRetry={handleRetry}
                    retrying={retryingSourceId === s.id}
                    indent={false}
                  />
                );
              }
              if (row.kind === "batch" && row.batch) {
                const b = row.batch;
                const isExpanded = expandedJobId === b.job_id;
                return (
                  <Fragment key={`batch-${b.job_id}`}>
                    <tr onClick={() => toggleJob(b.job_id)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50">
                      <td className="max-w-xs truncate px-4 py-2" title={b.origin_label}>
                        {renamingJobId === b.job_id ? (
                          <input
                            autoFocus
                            value={renameLabel}
                            onChange={(e) => setRenameLabel(e.target.value)}
                            onClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRenameBatch(b);
                              if (e.key === "Escape") setRenamingJobId(null);
                            }}
                            className="rounded border border-slate-300 px-2 py-1 text-sm"
                          />
                        ) : (
                          <>
                            <span className="mr-2 text-slate-400">{isExpanded ? "▾" : "▸"}</span>
                            <span className="font-medium text-slate-800">{b.origin_label}</span>
                            <span className="ml-2 text-xs text-slate-400">({b.source_count} pages)</span>
                          </>
                        )}
                      </td>
                      <td className="px-4 py-2 text-slate-500">{categoryName(b.category_id)}</td>
                      <td className="px-4 py-2 text-slate-500">—</td>
                      <td className="px-4 py-2 text-slate-500">{new Date(b.created_at).toLocaleDateString()}</td>
                      <td className="px-4 py-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            filterJobSources(b.job_id, "indexed");
                          }}
                          className={`rounded px-2 py-0.5 text-xs font-medium ${
                            isExpanded && jobSourcesFilter === "indexed"
                              ? "bg-green-600 text-white"
                              : "bg-green-50 text-green-700 hover:bg-green-100"
                          }`}
                        >
                          {b.indexed_count} indexed
                        </button>
                        {b.pending_count > 0 && (
                          // Not clickable-to-filter like the others: this
                          // count combines "pending" + "processing" sources,
                          // but the backend filter matches a single status
                          // column value, so filtering on "pending" alone
                          // would silently hide the "processing" ones.
                          <span className="ml-1 rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                            {b.pending_count} pending
                          </span>
                        )}
                        {b.failed_count > 0 && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              filterJobSources(b.job_id, "failed");
                            }}
                            className={`ml-1 rounded px-2 py-0.5 text-xs font-medium ${
                              isExpanded && jobSourcesFilter === "failed"
                                ? "bg-red-600 text-white"
                                : "bg-red-50 text-red-700 hover:bg-red-100"
                            }`}
                          >
                            {b.failed_count} failed
                          </button>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {renamingJobId === b.job_id ? (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRenameBatch(b);
                              }}
                              className="mr-2 text-blue-600"
                            >
                              Save
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setRenamingJobId(null);
                              }}
                              className="mr-3 text-slate-500"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setRenamingJobId(b.job_id);
                              setRenameLabel(b.origin_label);
                            }}
                            className="mr-3 text-blue-600"
                          >
                            Rename
                          </button>
                        )}
                        {b.failed_count > 0 && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRetryBatch(b);
                            }}
                            disabled={retryingJobId === b.job_id}
                            className="mr-3 text-blue-600 disabled:cursor-not-allowed disabled:text-slate-300"
                          >
                            {retryingJobId === b.job_id ? "Retrying..." : "Retry Failed"}
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteBatch(b);
                          }}
                          className="text-red-600"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-t border-slate-100 bg-slate-50">
                        <td colSpan={6} className="p-0">
                          {jobSourcesFilter && (
                            <div className="flex items-center justify-between px-8 py-2 text-xs text-slate-500">
                              <span>
                                Showing <span className="font-medium">{jobSourcesFilter}</span> pages only
                              </span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setJobSourcesFilter(null);
                                  setJobSources(null);
                                  loadJobSources(b.job_id, null, 1);
                                }}
                                className="text-blue-600"
                              >
                                Show all
                              </button>
                            </div>
                          )}
                          {jobSourcesLoading && (
                            <p className="px-8 py-3 text-xs text-slate-400">Loading pages...</p>
                          )}
                          {!jobSourcesLoading && jobSources && jobSources.length === 0 && (
                            <p className="px-8 py-3 text-xs text-slate-400">No pages match this filter.</p>
                          )}
                          {!jobSourcesLoading && jobSources && jobSources.length > 0 && (
                            <>
                              <table className="w-full text-sm">
                                <tbody>
                                  {jobSources.map((s) => (
                                    <SourceRow
                                      key={`job-source-${s.id}`}
                                      source={s}
                                      categoryName={categoryName}
                                      onDelete={handleDelete}
                                      onRetry={handleRetry}
                                      retrying={retryingSourceId === s.id}
                                      indent
                                    />
                                  ))}
                                </tbody>
                              </table>
                              {jobSourcesTotal > jobSourcesPageSize && (
                                <div className="px-8 py-2" onClick={(e) => e.stopPropagation()}>
                                  <Pagination
                                    page={jobSourcesPage}
                                    pageSize={jobSourcesPageSize}
                                    total={jobSourcesTotal}
                                    onPageChange={(p) => loadJobSources(b.job_id, jobSourcesFilter, p)}
                                  />
                                </div>
                              )}
                            </>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              }
              return null;
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
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
