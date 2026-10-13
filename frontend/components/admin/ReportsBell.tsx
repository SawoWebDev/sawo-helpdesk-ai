"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, Check } from "lucide-react";
import { apiFetch, apiGet } from "@/lib/api";
import { FEEDBACK_REASONS } from "@/components/chat/MessageBubble";

export interface ChatReportRow {
  id: number;
  chat_log_id: number;
  session_id: string;
  question_text: string;
  answer_text: string;
  reference_urls: string[];
  reason: string | null;
  comment: string | null;
  status: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

const POLL_MS = 30000;

export const REPORT_REASON_LABELS: Record<string, string> = Object.fromEntries(
  FEEDBACK_REASONS.map((r) => [r.value, r.label])
);

// "2026-09-17T10:32:00Z" -> "2h ago" / "3d ago" — same scheme as the dashboard's timeAgo.
export function reportTimeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Bell with a red badge for open "report a problem" entries (chat_reports
 * table — see backend/app/models/chat_report.py). Polls the open count so it
 * stays current across admin pages, and opens a small panel to triage
 * without needing a dedicated Reports page. */
export default function ReportsBell() {
  const [open, setOpen] = useState(false);
  const [total, setTotal] = useState(0);
  const [reports, setReports] = useState<ChatReportRow[] | null>(null);
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  function refreshCount() {
    apiGet<Paginated<ChatReportRow>>("/api/logs/reports?status=open&page=1&page_size=1")
      .then((data) => setTotal(data.total))
      .catch(() => {});
  }

  useEffect(() => {
    refreshCount();
    const interval = setInterval(refreshCount, POLL_MS);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  function loadReports() {
    setReports(null);
    apiGet<Paginated<ChatReportRow>>("/api/logs/reports?status=open&page=1&page_size=8")
      .then((data) => setReports(data.items))
      .catch(() => setReports([]));
  }

  function toggleOpen() {
    setOpen((v) => {
      const next = !v;
      if (next) loadReports();
      return next;
    });
  }

  async function resolveReport(id: number) {
    setResolvingId(id);
    try {
      await apiFetch(`/api/logs/reports/${id}/resolve`, { method: "POST" });
      setReports((prev) => (prev ? prev.filter((r) => r.id !== id) : prev));
      setTotal((t) => Math.max(0, t - 1));
    } catch {
      // leave it in the list so the user can retry
    } finally {
      setResolvingId(null);
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={toggleOpen}
        aria-label={total > 0 ? `Reported answers (${total} open)` : "Reported answers"}
        title="Reported answers"
        className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white/85 hover:bg-white/15 hover:text-white"
      >
        <Bell size={18} />
        {total > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white">
            {total > 9 ? "9+" : total}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-20 w-80 max-w-[90vw] rounded-lg border border-slate-200 bg-white py-2 shadow-lg dark:border-white/10 dark:bg-night-surface">
          <p className="px-3 pb-1.5 text-sm font-semibold text-slate-700 dark:text-slate-200">
            Reported answers{total > 0 ? ` (${total} open)` : ""}
          </p>
          <div className="max-h-80 overflow-y-auto">
            {reports === null && (
              <p className="px-3 py-4 text-center text-sm text-slate-400 dark:text-slate-500">Loading…</p>
            )}
            {reports && reports.length === 0 && (
              <p className="px-3 py-4 text-center text-sm text-slate-400 dark:text-slate-500">No open reports.</p>
            )}
            {reports?.map((r) => (
              <Link
                key={r.id}
                href={`/admin/reports?id=${r.id}`}
                onClick={() => setOpen(false)}
                className="block border-t border-slate-100 px-3 py-2 text-sm first:border-t-0 hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
              >
                <p className="line-clamp-2 font-medium text-slate-700 dark:text-slate-200">{r.question_text}</p>
                <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
                  {r.reason ? REPORT_REASON_LABELS[r.reason] ?? r.reason : "No reason given"} · {reportTimeAgo(r.created_at)}
                </p>
                {r.comment && (
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">&ldquo;{r.comment}&rdquo;</p>
                )}
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    resolveReport(r.id);
                  }}
                  disabled={resolvingId === r.id}
                  className="relative z-10 mt-1.5 flex items-center gap-1 text-xs font-medium text-sawo-dark hover:underline disabled:opacity-50 dark:text-sawo-light"
                >
                  <Check size={12} /> {resolvingId === r.id ? "Resolving…" : "Mark resolved"}
                </button>
              </Link>
            ))}
          </div>
          <Link
            href="/admin/reports"
            onClick={() => setOpen(false)}
            className="block border-t border-slate-100 px-3 py-2 text-center text-xs font-medium text-sawo-dark hover:underline dark:border-white/10 dark:text-sawo-light"
          >
            View all reports
          </Link>
        </div>
      )}
    </div>
  );
}
