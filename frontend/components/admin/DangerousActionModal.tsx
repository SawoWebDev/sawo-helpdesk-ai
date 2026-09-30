"use client";

import { FormEvent, useState } from "react";
import { X } from "lucide-react";
import { ApiError } from "@/lib/api";

export const DANGEROUS_ACTION_PHRASE = "DELETE THIS";

export interface DangerousActionPayload {
  confirm_text: string;
  username: string;
  password: string;
}

// Extra confirmation in front of any bulk-delete action: typing the exact
// phrase guards against a stray click, and re-entering the admin's own
// credentials guards against a session left open on someone else's screen —
// the backend re-checks both (see require_dangerous_action_confirmation).
export default function DangerousActionModal({
  title,
  description,
  confirmLabel = "Delete",
  onClose,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel?: string;
  onClose: () => void;
  onConfirm: (payload: DangerousActionPayload) => Promise<void>;
}) {
  const [phraseInput, setPhraseInput] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const phraseMatches = phraseInput === DANGEROUS_ACTION_PHRASE;
  const canSubmit = phraseMatches && username.trim() !== "" && password !== "" && !submitting;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({ confirm_text: phraseInput, username: username.trim(), password });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to complete the action");
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl bg-white shadow-2xl dark:bg-night-surface"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-red-200 px-5 py-4 dark:border-red-500/20">
          <h2 className="text-base font-semibold text-red-700 dark:text-red-400">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:text-slate-500 dark:hover:bg-white/10"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-5">
          <p className="text-sm text-slate-600 dark:text-slate-300">{description}</p>

          {error && (
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">
              {error}
            </p>
          )}

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Type <span className="font-mono font-semibold">{DANGEROUS_ACTION_PHRASE}</span> to confirm
            </label>
            <input
              type="text"
              value={phraseInput}
              onChange={(e) => setPhraseInput(e.target.value)}
              placeholder={DANGEROUS_ACTION_PHRASE}
              autoComplete="off"
              autoFocus
              className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Your admin username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Your admin password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-white/15 dark:text-slate-300 dark:hover:bg-white/5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Working..." : confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
