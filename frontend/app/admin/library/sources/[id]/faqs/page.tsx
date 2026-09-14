"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiGet, apiPut, ApiError } from "@/lib/api";

interface LibrarySource {
  id: number;
  source_type: "file" | "url";
  origin_url: string | null;
  original_filename: string | null;
}

interface SourceFaq {
  id: number;
  question: string;
  answer: string;
  status: "draft" | "published";
}

export default function SourceFaqsPage() {
  const params = useParams<{ id: string }>();
  const sourceId = Number(params.id);

  const [source, setSource] = useState<LibrarySource | null>(null);
  const [faqs, setFaqs] = useState<SourceFaq[] | null>(null);
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
        const [sourceData, faqData] = await Promise.all([
          apiGet<LibrarySource>(`/api/library/sources/${sourceId}`),
          apiGet<SourceFaq[]>(`/api/library/sources/${sourceId}/faqs`),
        ]);
        setSource(sourceData);
        setFaqs(faqData);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load FAQs for this source");
      } finally {
        setLoading(false);
      }
    }
    if (Number.isFinite(sourceId)) load();
  }, [sourceId]);

  function startEditingFaq(faq: SourceFaq) {
    setEditingFaqId(faq.id);
    setEditQuestion(faq.question);
    setEditAnswer(faq.answer);
  }

  function cancelEditingFaq() {
    setEditingFaqId(null);
  }

  async function saveEditedFaq(faq: SourceFaq) {
    setSavingFaqId(faq.id);
    setError(null);
    try {
      const updated = await apiPut<SourceFaq>(`/api/faqs/${faq.id}`, {
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

  async function toggleFaqStatus(faq: SourceFaq) {
    const nextStatus = faq.status === "published" ? "draft" : "published";
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
      {source && (
        <p className="mb-6 max-w-2xl truncate text-sm text-slate-500" title={source.original_filename ?? source.origin_url ?? ""}>
          {source.source_type === "file" ? source.original_filename : source.origin_url}
        </p>
      )}

      {error && <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Loading...</p>}
      {!loading && faqs && faqs.length === 0 && (
        <p className="text-sm text-slate-400">No FAQs generated for this source yet.</p>
      )}

      {!loading && faqs && faqs.length > 0 && (
        <div className="flex max-w-2xl flex-col gap-3">
          {faqs.map((faq) => {
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
                      <span
                        className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
                          faq.status === "published" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                        }`}
                      >
                        {faq.status}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600">{faq.answer}</p>
                    <div className="mt-2 flex gap-3 text-xs">
                      <button onClick={() => startEditingFaq(faq)} className="text-blue-600 hover:underline">
                        Edit
                      </button>
                      <button
                        onClick={() => toggleFaqStatus(faq)}
                        disabled={isSaving}
                        className="text-blue-600 hover:underline disabled:opacity-50"
                      >
                        {isSaving ? "Saving..." : faq.status === "published" ? "Unpublish" : "Publish"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
