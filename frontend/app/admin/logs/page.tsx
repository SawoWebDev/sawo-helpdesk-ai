"use client";

import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/useCurrentUser";
import Pagination from "@/components/admin/Pagination";

interface ChatLog {
  id: number;
  question_text: string;
  answer_text: string;
  matched_faq_ids: number[];
  matched_vault_ids: number[];
  confidence_score: number | null;
  engine_used: string;
  created_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

type FilterMode = "none" | "onward" | "range";

export default function LogsPage() {
  const { user } = useCurrentUser();
  const [logs, setLogs] = useState<ChatLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterMode, setFilterMode] = useState<FilterMode>("none");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingLogId, setSavingLogId] = useState<number | null>(null);
  const [savedLogIds, setSavedLogIds] = useState<Set<number>>(new Set());
  const pageSize = 20;

  function loadLogs() {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (filterMode === "onward" && startAt) {
      params.set("start_at", new Date(startAt).toISOString());
    }
    if (filterMode === "range") {
      if (startAt) params.set("start_at", new Date(startAt).toISOString());
      if (endAt) params.set("end_at", new Date(endAt).toISOString());
    }
    apiGet<Paginated<ChatLog>>(`/api/logs?${params.toString()}`).then((data) => {
      setLogs(data.items);
      setTotal(data.total);
    });
  }

  useEffect(loadLogs, [page, filterMode, startAt, endAt]);

  function handleModeChange(mode: FilterMode) {
    setFilterMode(mode);
    setStartAt("");
    setEndAt("");
    setPage(1);
  }

  async function handleSaveAsFaq(log: ChatLog) {
    if (!confirm("Save this answer as a new FAQ entry (draft, for review)?")) return;
    setSavingLogId(log.id);
    setError(null);
    try {
      await apiPost(`/api/logs/${log.id}/save-as-faq`, {});
      setSavedLogIds((prev) => new Set(prev).add(log.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save as FAQ");
    } finally {
      setSavingLogId(null);
    }
  }

  async function handleClearAll() {
    if (!confirm("Permanently delete ALL chat logs? This cannot be undone.")) return;
    setClearing(true);
    setError(null);
    try {
      await apiDelete("/api/logs");
      setPage(1);
      loadLogs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to clear logs");
    } finally {
      setClearing(false);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Chat Logs</h1>
        {user?.role === "admin" && (
          <button
            onClick={handleClearAll}
            disabled={clearing || total === 0}
            className="rounded border border-red-300 px-3 py-2 text-sm font-medium text-red-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {clearing ? "Clearing..." : "Clear all logs"}
          </button>
        )}
      </div>

      {error && <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

      <div className="mb-4 flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Date/Time Filter</label>
          <select
            value={filterMode}
            onChange={(e) => handleModeChange(e.target.value as FilterMode)}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="none">No filter</option>
            <option value="onward">From date onward</option>
            <option value="range">Date range (start–end)</option>
          </select>
        </div>

        {filterMode === "onward" && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">From</label>
            <input
              type="datetime-local"
              value={startAt}
              onChange={(e) => {
                setPage(1);
                setStartAt(e.target.value);
              }}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
        )}

        {filterMode === "range" && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500">Start</label>
              <input
                type="datetime-local"
                value={startAt}
                onChange={(e) => {
                  setPage(1);
                  setStartAt(e.target.value);
                }}
                className="rounded border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500">End</label>
              <input
                type="datetime-local"
                value={endAt}
                onChange={(e) => {
                  setPage(1);
                  setEndAt(e.target.value);
                }}
                className="rounded border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
          </>
        )}
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-2">Question</th>
              <th className="px-4 py-2">Answer</th>
              <th className="px-4 py-2">Confidence</th>
              <th className="px-4 py-2">Sources</th>
              <th className="px-4 py-2">Engine</th>
              <th className="px-4 py-2">Time</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => {
              const hasMatch = log.matched_faq_ids.length > 0 || log.matched_vault_ids.length > 0;
              const isSaved = savedLogIds.has(log.id);
              const isSaving = savingLogId === log.id;
              return (
                <tr key={log.id} className="border-t border-slate-100 align-top">
                  <td className="max-w-xs px-4 py-2">{log.question_text}</td>
                  <td className="max-w-xs truncate px-4 py-2">{log.answer_text}</td>
                  <td className="px-4 py-2">
                    {log.confidence_score !== null ? log.confidence_score.toFixed(2) : "—"}
                  </td>
                  <td className="px-4 py-2 text-slate-500">
                    {!hasMatch
                      ? "—"
                      : [
                          log.matched_faq_ids.length > 0 ? `${log.matched_faq_ids.length} FAQ` : null,
                          log.matched_vault_ids.length > 0 ? `${log.matched_vault_ids.length} Vault` : null,
                        ]
                          .filter(Boolean)
                          .join(", ")}
                  </td>
                  <td className="px-4 py-2">{log.engine_used}</td>
                  <td className="px-4 py-2 text-slate-500">{new Date(log.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2 text-right">
                    {hasMatch && (
                      <button
                        onClick={() => handleSaveAsFaq(log)}
                        disabled={isSaving || isSaved}
                        className="whitespace-nowrap text-blue-600 disabled:cursor-not-allowed disabled:text-slate-300"
                      >
                        {isSaved ? "Saved" : isSaving ? "Saving..." : "Save as FAQ"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {logs.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-slate-400">
                  No chat logs found for this filter.
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
