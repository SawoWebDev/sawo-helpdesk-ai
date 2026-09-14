"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiGet, apiPut, ApiError } from "@/lib/api";

interface JobFaq {
  id: number;
  question: string;
  answer: string;
  status: "draft" | "published";
  source_id: number;
  source_url: string | null;
  source_filename: string | null;
}

export default function JobFaqsPage() {
  const params = useParams<{ id: string }>();
  const jobId = Number(params.id);

  const [faqs, setFaqs] = useState<JobFaq[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingFaqId, setEditingFaqId] = useState<number | null>(null);
  const [editQuestion, setEditQuestion] = useState("");
  const [editAnswer, setEditAnswer] = useState("");
  const [savingFaqId, setSavingFaqId] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await apiGet<JobFaq[]>(`/api/library/jobs/${jobId}/faqs`);
        setFaqs(data);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load FAQs for this crawl");
      } finally {
        setLoading(false);
      }
    }
    if (Number.isFinite(jobId)) load();
  }, [jobId]);

  const grouped = useMemo(() => {
    if (!faqs) return [];
    const bySource = new Map<number, { label: string; faqs: JobFaq[] }>();
    for (const faq of faqs) {
      const label = faq.source_filename ?? faq.source_url ?? `Source #${faq.source_id}`;
      if (!bySource.has(faq.source_id)) bySource.set(faq.source_id, { label, faqs: [] });
      bySource.get(faq.source_id)!.faqs.push(faq);
    }
    return Array.from(bySource.entries()).map(([sourceId, group]) => ({ sourceId, ...group }));
  }, [faqs]);

  function startEditingFaq(faq: JobFaq) {
    setEditingFaqId(faq.id);
    setEditQuestion(faq.question);
    setEditAnswer(faq.answer);
  }

  function cancelEditingFaq() {
    setEditingFaqId(null);
  }

  async function saveEditedFaq(faq: JobFaq) {
    setSavingFaqId(faq.id);
    setError(null);
    try {
      const updated = await apiPut<{ question: string; answer: string }>(`/api/faqs/${faq.id}`, {
        question: editQuestion,
        answer: editAnswer,
      });
      setFaqs((prev) =>
        prev ? prev.map((f) => (f.id === faq.id ? { ...f, question: updated.question, answer: updated.answer } : f)) : prev
      );
      setEditingFaqId(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save FAQ");
    } finally {
      setSavingFaqId(null);
    }
  }

  async function setFaqStatus(faq: JobFaq, nextStatus: "draft" | "published") {
    if (nextStatus === faq.status) return;
    setSavingFaqId(faq.id);
    setError(null);
    try {
      await apiPut(`/api/faqs/${faq.id}`, { status: nextStatus });
      setFaqs((prev) => (prev ? prev.map((f) => (f.id === faq.id ? { ...f, status: nextStatus } : f)) : prev));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update FAQ status");
    } finally {
      setSavingFaqId(null);
    }
  }

  return (
    <div>
      <Link href="/admin/library" className="mb-4 inline-block text-sm text-blue-600 hover:underline">
        ← Back to Library
      </Link>

      <h1 className="mb-1 text-xl font-semibold text-slate-800">Generated FAQs</h1>
      {faqs && (
        <p className="mb-6 text-sm text-slate-500">
          {faqs.length} FAQ{faqs.length === 1 ? "" : "s"} across {grouped.length} page{grouped.length === 1 ? "" : "s"}
        </p>
      )}

      {error && <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Loading...</p>}
      {!loading && faqs && faqs.length === 0 && (
        <p className="text-sm text-slate-400">No FAQs generated for this crawl yet.</p>
      )}

      {!loading && grouped.length > 0 && (
        <div className="flex max-w-3xl flex-col gap-6">
          {grouped.map((group) => (
            <div key={group.sourceId}>
              <div className="mb-2 flex items-center justify-between">
                <p className="max-w-xl truncate text-sm font-medium text-slate-600" title={group.label}>
                  {group.label}
                </p>
                <Link
                  href={`/admin/library/sources/${group.sourceId}/faqs`}
                  className="shrink-0 text-xs text-blue-600 hover:underline"
                >
                  View page →
                </Link>
              </div>
              <div className="flex flex-col gap-3">
                {group.faqs.map((faq) => {
                  const isEditing = editingFaqId === faq.id;
                  const isSaving = savingFaqId === faq.id;
                  return (
                    <div key={faq.id} className="rounded-lg border border-slate-200 bg-white p-4">
                      {isEditing ? (
                        <div className="flex flex-col gap-2">
                          <div className="flex flex-col gap-1">
                            <label className="text-xs text-slate-500">Question</label>
                            <input
                              value={editQuestion}
                              onChange={(e) => setEditQuestion(e.target.value)}
                              className="rounded border border-slate-300 px-2 py-1 text-sm font-medium text-slate-800"
                            />
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className="text-xs text-slate-500">Answer</label>
                            <textarea
                              value={editAnswer}
                              onChange={(e) => setEditAnswer(e.target.value)}
                              rows={4}
                              className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-700"
                            />
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => saveEditedFaq(faq)}
                              disabled={isSaving || !editQuestion.trim() || !editAnswer.trim()}
                              className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                            >
                              {isSaving ? "Saving..." : "Save"}
                            </button>
                            <button
                              onClick={cancelEditingFaq}
                              disabled={isSaving}
                              className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-600"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="mb-1 flex items-start justify-between gap-2">
                            <p className="text-sm font-medium text-slate-800">{faq.question}</p>
                            <select
                              value={faq.status}
                              onChange={(e) => setFaqStatus(faq, e.target.value as "draft" | "published")}
                              disabled={isSaving}
                              className={`shrink-0 rounded border-0 px-2 py-0.5 text-xs font-medium disabled:opacity-50 ${
                                faq.status === "published" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                              }`}
                            >
                              <option value="draft">draft</option>
                              <option value="published">published</option>
                            </select>
                          </div>
                          <p className="text-sm text-slate-600">{faq.answer}</p>
                          <div className="mt-2 flex gap-3 text-xs">
                            <button onClick={() => startEditingFaq(faq)} className="text-blue-600 hover:underline">
                              Edit
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
