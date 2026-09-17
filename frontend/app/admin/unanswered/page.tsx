"use client";

import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import CategorySelect, { CategoryOption } from "@/components/admin/CategorySelect";
import ImageUploader from "@/components/admin/ImageUploader";
import Pagination from "@/components/admin/Pagination";

interface UnansweredQuestion {
  id: number;
  question_text: string;
  status: string;
  category_id: number | null;
  confidence_score: number | null;
  created_at: string;
  resolved_at: string | null;
  resulting_faq_id: number | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

export default function UnansweredPage() {
  const [items, setItems] = useState<UnansweredQuestion[]>([]);
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [resolveCategoryId, setResolveCategoryId] = useState<number | null>(null);
  const [imageUrls, setImageUrls] = useState<string[]>([]);
  const [referenceUrls, setReferenceUrls] = useState<string[]>([]);
  const pageSize = 20;

  async function load() {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (statusFilter) params.set("status", statusFilter);
    const data = await apiGet<Paginated<UnansweredQuestion>>(`/api/unanswered?${params.toString()}`);
    setItems(data.items);
    setTotal(data.total);
  }

  useEffect(() => {
    apiGet<CategoryOption[]>("/api/categories").then(setCategories);
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter]);

  function startResolve(item: UnansweredQuestion) {
    setExpandedId(item.id);
    setAnswer("");
    setResolveCategoryId(item.category_id);
    setImageUrls([]);
    setReferenceUrls([]);
  }

  async function submitResolve(id: number) {
    await apiPost(`/api/unanswered/${id}/resolve`, {
      answer,
      category_id: resolveCategoryId,
      image_urls: imageUrls,
      reference_urls: referenceUrls,
    });
    setExpandedId(null);
    await load();
  }

  async function assignCategory(id: number, categoryId: number | null) {
    await apiPut(`/api/unanswered/${id}/category`, { category_id: categoryId });
    await load();
  }

  async function dismiss(id: number) {
    if (!confirm("Dismiss this question?")) return;
    await apiDelete(`/api/unanswered/${id}`);
    await load();
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800 dark:text-slate-100">Unanswered Questions</h1>
        <select
          value={statusFilter}
          onChange={(e) => {
            setPage(1);
            setStatusFilter(e.target.value);
          }}
          className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
        >
          <option value="pending">Pending</option>
          <option value="answered">Answered</option>
          <option value="">All</option>
        </select>
      </div>

      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <div key={item.id} className="rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{item.question_text}</p>
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  {new Date(item.created_at).toLocaleString()} · status: {item.status}
                  {item.confidence_score !== null && ` · confidence: ${item.confidence_score.toFixed(2)}`}
                </p>
              </div>
              {item.status === "pending" && (
                <div className="flex items-center gap-2">
                  <CategorySelect
                    categories={categories}
                    value={item.category_id}
                    onChange={(id) => assignCategory(item.id, id)}
                  />
                  <button onClick={() => startResolve(item)} className="text-sm text-sawo-dark dark:text-sawo-light">
                    Answer
                  </button>
                  <button onClick={() => dismiss(item.id)} className="text-sm text-red-600 dark:text-red-400">
                    Dismiss
                  </button>
                </div>
              )}
            </div>

            {expandedId === item.id && (
              <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4 dark:border-white/10">
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Write the answer..."
                  rows={4}
                  className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
                />
                <CategorySelect
                  categories={categories}
                  value={resolveCategoryId}
                  onChange={setResolveCategoryId}
                />
                <ImageUploader urls={imageUrls} onChange={setImageUrls} />
                <div className="flex gap-2">
                  <button
                    onClick={() => submitResolve(item.id)}
                    disabled={!answer.trim()}
                    className="rounded bg-sawo px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sawo-dark disabled:opacity-50 dark:bg-sawo-dark dark:hover:bg-sawo-darker"
                  >
                    Promote to FAQ
                  </button>
                  <button onClick={() => setExpandedId(null)} className="rounded border border-slate-300 px-4 py-2 text-sm dark:border-white/15 dark:text-slate-300 dark:hover:bg-white/5">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}

        {items.length === 0 && <p className="text-center text-slate-400 dark:text-slate-500">No questions found.</p>}
      </div>

      <div className="mt-4 rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
        <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
      </div>
    </div>
  );
}
