"use client";

import { FormEvent, KeyboardEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiPost, apiPut, ApiError } from "@/lib/api";
import CategorySelect, { CategoryOption } from "./CategorySelect";
import ImageUploader from "./ImageUploader";

export interface FAQFormValues {
  question: string;
  answer: string;
  category_id: number | null;
  image_urls: string[];
  reference_urls: string[];
}

export default function FAQForm({
  faqId,
  initial,
}: {
  faqId?: number;
  initial?: FAQFormValues;
}) {
  const router = useRouter();
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [question, setQuestion] = useState(initial?.question ?? "");
  const [answer, setAnswer] = useState(initial?.answer ?? "");
  const [categoryId, setCategoryId] = useState<number | null>(initial?.category_id ?? null);
  const [imageUrls, setImageUrls] = useState<string[]>(initial?.image_urls ?? []);
  const [referenceUrls, setReferenceUrls] = useState<string[]>(initial?.reference_urls ?? []);
  const [refInput, setRefInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    apiGet<CategoryOption[]>("/api/categories").then(setCategories);
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const payload = {
      question,
      answer,
      category_id: categoryId,
      image_urls: imageUrls,
      reference_urls: referenceUrls,
    };
    try {
      if (faqId) {
        await apiPut(`/api/faqs/${faqId}`, payload);
      } else {
        await apiPost("/api/faqs", payload);
      }
      router.push("/admin/faqs");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save FAQ");
    } finally {
      setSubmitting(false);
    }
  }

  function addReferenceUrl() {
    if (!refInput.trim()) return;
    setReferenceUrls([...referenceUrls, refInput.trim()]);
    setRefInput("");
  }

  function handleRefInputKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    // Without this, Enter here submits the whole FAQ form (the default
    // browser behavior for a text input in a <form>) instead of adding the
    // URL — silently discarding whatever was just typed here.
    e.preventDefault();
    addReferenceUrl();
  }

  return (
    <form onSubmit={handleSubmit} className="flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-slate-700">Question</label>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          required
          rows={2}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-slate-700">Answer</label>
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          required
          rows={6}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <p className="text-xs text-slate-400">Markdown supported (bold, links, lists, etc).</p>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-slate-700">Category</label>
        <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-slate-700">Images</label>
        <ImageUploader urls={imageUrls} onChange={setImageUrls} />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-slate-700">Reference URLs</label>
        <div className="flex flex-col gap-1">
          {referenceUrls.map((url) => (
            <div key={url} className="flex items-center gap-2 text-sm">
              <a href={url} target="_blank" rel="noopener noreferrer" className="flex-1 truncate text-blue-600 underline">
                {url}
              </a>
              <button
                type="button"
                onClick={() => setReferenceUrls(referenceUrls.filter((u) => u !== url))}
                className="text-red-600"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={refInput}
            onChange={(e) => setRefInput(e.target.value)}
            onKeyDown={handleRefInputKeyDown}
            placeholder="https://..."
            className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
          />
          <button type="button" onClick={addReferenceUrl} className="rounded border border-slate-300 px-3 py-1 text-sm">
            Add
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {submitting ? "Saving..." : "Save"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/admin/faqs")}
          className="rounded border border-slate-300 px-4 py-2 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
