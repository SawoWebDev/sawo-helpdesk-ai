"use client";

import { FormEvent, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { apiDelete, apiFetch, apiGet, apiPost, ApiError } from "@/lib/api";

interface Phrasing {
  id: number;
  phrasing: string;
  enabled: boolean;
  has_embedding: boolean;
}

// Other ways staff ask this FAQ's question. A match on one serves this FAQ's
// answer directly, with no AI call — so each one is added by a person, and the
// backend refuses wordings that don't fit this FAQ (different error code,
// controller, model or symptom, or an extra question) with the reason.
export default function FAQPhrasingsPanel({ faqId }: { faqId: number }) {
  const [items, setItems] = useState<Phrasing[] | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Phrasing[]>(`/api/faqs/${faqId}/phrasings`)
      .then(setItems)
      .catch(() => setItems([]));
  }, [faqId]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    run(async () => {
      const created = await apiPost<Phrasing>(`/api/faqs/${faqId}/phrasings`, { phrasing: draft.trim() });
      setItems((prev) => [...(prev ?? []), created]);
      setDraft("");
    });
  }

  function handleToggle(p: Phrasing) {
    run(async () => {
      const updated = await apiFetch<Phrasing>(`/api/faqs/${faqId}/phrasings/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !p.enabled }),
      });
      setItems((prev) => (prev ?? []).map((x) => (x.id === p.id ? updated : x)));
    });
  }

  function handleDelete(p: Phrasing) {
    if (!confirm(`Remove this phrasing?\n\n"${p.phrasing}"`)) return;
    run(async () => {
      await apiDelete(`/api/faqs/${faqId}/phrasings/${p.id}`);
      setItems((prev) => (prev ?? []).filter((x) => x.id !== p.id));
    });
  }

  return (
    <div className="mt-6 max-w-2xl rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface">
      <h2 className="mb-1 text-sm font-semibold text-slate-800 dark:text-slate-100">Alternate phrasings</h2>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Other ways staff ask this same question. When someone asks one of these, the bot replies with this FAQ&apos;s
        answer instantly, without using the AI. Only add wordings that mean exactly this question.
      </p>

      {error && (
        <p className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">{error}</p>
      )}

      {items === null ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">Loading...</p>
      ) : items.length === 0 ? (
        <p className="mb-3 text-sm text-slate-400 dark:text-slate-500">No alternate phrasings yet.</p>
      ) : (
        <ul className="mb-3 divide-y divide-slate-100 rounded border border-slate-200 dark:divide-white/10 dark:border-white/10">
          {items.map((p) => (
            <li key={p.id} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className={`flex-1 ${p.enabled ? "text-slate-800 dark:text-slate-100" : "text-slate-400 line-through dark:text-slate-500"}`}>
                {p.phrasing}
              </span>
              <button
                type="button"
                onClick={() => handleToggle(p)}
                disabled={busy}
                className="shrink-0 text-xs font-medium text-sawo-dark hover:underline disabled:opacity-50 dark:text-sawo-light"
              >
                {p.enabled ? "Disable" : "Enable"}
              </button>
              <button
                type="button"
                onClick={() => handleDelete(p)}
                disabled={busy}
                aria-label="Remove phrasing"
                className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-red-600 disabled:opacity-50 dark:hover:bg-white/10 dark:hover:text-red-400"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="e.g. My NB heater is humming loudly. How do I fix it?"
          maxLength={500}
          className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="shrink-0 rounded bg-sawo px-3 py-2 text-sm font-medium text-white hover:bg-sawo-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          Add
        </button>
      </form>
    </div>
  );
}
