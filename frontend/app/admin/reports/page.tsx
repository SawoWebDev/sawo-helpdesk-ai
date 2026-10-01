"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, ChevronUp, ExternalLink, RotateCcw, Trash2 } from "lucide-react";
import { apiDelete, apiFetch, apiGet, ApiError } from "@/lib/api";
import { formatDisplayDate, formatTime } from "@/components/admin/logs/format";
import { REPORT_REASON_LABELS, reportTimeAgo, type ChatReportRow } from "@/components/admin/ReportsBell";
import Pagination from "@/components/admin/Pagination";
import PageHeader from "@/components/admin/PageHeader";

interface Paginated<T> {
  items: T[];
  total: number;
}

const PAGE_SIZE = 20;

function shortId(id: string): string {
  return id.slice(0, 8);
}

const STATUS_TABS: { value: "open" | "resolved" | ""; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "resolved", label: "Resolved" },
  { value: "", label: "All" },
];

export default function ReportsPage() {
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<"open" | "resolved" | "">("open");
  const [reports, setReports] = useState<ChatReportRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [busyId, setBusyId] = useState<number | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (statusFilter) params.set("status", statusFilter);
    apiGet<Paginated<ChatReportRow>>(`/api/logs/reports?${params.toString()}`)
      .then((data) => {
        setReports(data.items);
        setTotal(data.total);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load reports"))
      .finally(() => setLoading(false));
  }

  useEffect(load, [page, statusFilter]);

  // Deep-linked from the notification bell (?id=123): show "All" so the
  // report is visible regardless of its current status, and expand it so
  // it's not buried among the others on the page.
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("id");
    const id = requested ? Number(requested) : null;
    if (!id || Number.isNaN(id)) return;
    setHighlightId(id);
    setStatusFilter("");
    setExpandedIds((prev) => new Set(prev).add(id));
  }, []);

  function toggleExpanded(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function setStatus(id: number, next: "open" | "resolved") {
    setBusyId(id);
    setError(null);
    try {
      await apiFetch(`/api/logs/reports/${id}/${next === "resolved" ? "resolve" : "reopen"}`, { method: "POST" });
      if (statusFilter && statusFilter !== next) {
        setReports((prev) => prev.filter((r) => r.id !== id));
        setTotal((t) => Math.max(0, t - 1));
      } else {
        setReports((prev) => prev.map((r) => (r.id === id ? { ...r, status: next } : r)));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update report");
    } finally {
      setBusyId(null);
    }
  }

  async function deleteReport(id: number) {
    if (!confirm("Delete this report? This cannot be undone.")) return;
    setBusyId(id);
    setError(null);
    try {
      await apiDelete(`/api/logs/reports/${id}`);
      setReports((prev) => prev.filter((r) => r.id !== id));
      setTotal((t) => Math.max(0, t - 1));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete report");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        icon="fa-solid fa-flag"
        title="Reports"
        description='Staff-submitted "report a problem" flags on chat answers.'
      />

      {error && (
        <p className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">{error}</p>
      )}

      <div className="mb-3 flex gap-1.5">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => {
              setStatusFilter(tab.value);
              setPage(1);
            }}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
              statusFilter === tab.value
                ? "border-sawo bg-sawo-bg text-sawo-dark dark:border-sawo-light/50 dark:bg-white/10 dark:text-sawo-light"
                : "border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-white/10 dark:text-slate-400 dark:hover:bg-white/5"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
        {loading && reports.length === 0 && (
          <p className="p-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading…</p>
        )}
        {!loading && reports.length === 0 && (
          <p className="p-6 text-center text-sm text-slate-400 dark:text-slate-500">
            {statusFilter === "open" ? "No open reports." : statusFilter === "resolved" ? "No resolved reports." : "No reports yet."}
          </p>
        )}
        <ul className="divide-y divide-slate-100 dark:divide-white/10">
          {reports.map((r) => {
            const expanded = expandedIds.has(r.id);
            const highlighted = r.id === highlightId;
            return (
              <li
                key={r.id}
                className={`px-4 py-3 ${highlighted ? "bg-amber-50/60 dark:bg-amber-500/10" : ""}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <button onClick={() => toggleExpanded(r.id)} className="flex min-w-0 flex-1 items-start gap-2 text-left">
                    {expanded ? (
                      <ChevronUp size={14} className="mt-1 shrink-0 text-slate-400" />
                    ) : (
                      <ChevronDown size={14} className="mt-1 shrink-0 text-slate-400" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className={`font-medium text-slate-700 dark:text-slate-200 ${expanded ? "" : "line-clamp-2"}`}>
                        {r.question_text}
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                        <span
                          className={`rounded-full px-1.5 py-0.5 font-medium ${
                            r.status === "open"
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
                              : "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
                          }`}
                        >
                          {r.status === "open" ? "Open" : "Resolved"}
                        </span>
                        {r.reason && <span>{REPORT_REASON_LABELS[r.reason] ?? r.reason}</span>}
                        <span>{reportTimeAgo(r.created_at)}</span>
                        <span>· {formatDisplayDate(r.created_at)} {formatTime(r.created_at)}</span>
                        {r.status === "resolved" && r.resolved_by && (
                          <span>
                            · resolved by {r.resolved_by}
                            {r.resolved_at ? ` on ${formatDisplayDate(r.resolved_at)}` : ""}
                          </span>
                        )}
                      </p>
                    </div>
                  </button>
                  <div className="flex shrink-0 items-center gap-1">
                    {r.status === "open" ? (
                      <button
                        onClick={() => setStatus(r.id, "resolved")}
                        disabled={busyId === r.id}
                        title="Mark resolved"
                        className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-sawo-dark hover:bg-sawo-bg disabled:opacity-50 dark:text-sawo-light dark:hover:bg-white/10"
                      >
                        <Check size={13} /> Resolve
                      </button>
                    ) : (
                      <button
                        onClick={() => setStatus(r.id, "open")}
                        disabled={busyId === r.id}
                        title="Reopen"
                        className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-white/10"
                      >
                        <RotateCcw size={13} /> Reopen
                      </button>
                    )}
                    <button
                      onClick={() => deleteReport(r.id)}
                      disabled={busyId === r.id}
                      title="Delete report"
                      className="rounded p-1.5 text-red-500 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-500/10"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {expanded && (
                  <div className="mt-2 ml-5 space-y-2 text-sm">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Answer</p>
                      <p className="whitespace-pre-wrap text-slate-600 dark:text-slate-300">{r.answer_text}</p>
                    </div>
                    {r.comment && (
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                          Staff comment
                        </p>
                        <p className="whitespace-pre-wrap text-slate-600 dark:text-slate-300">&ldquo;{r.comment}&rdquo;</p>
                      </div>
                    )}
                    {r.session_id && (
                      <Link
                        href={`/admin/logs?session=${encodeURIComponent(r.session_id)}`}
                        className="flex items-center gap-1 text-xs font-medium text-sawo-dark hover:underline dark:text-sawo-light"
                      >
                        <ExternalLink size={11} /> View conversation #{shortId(r.session_id)}
                      </Link>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
      </div>
    </div>
  );
}
