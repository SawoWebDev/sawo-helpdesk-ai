"use client";

import { Fragment, useEffect, useState } from "react";
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
  session_id: string | null;
  ip_address: string | null;
  created_at: string;
}

interface SessionSummary {
  session_id: string;
  ip_address: string | null;
  message_count: number;
  first_question: string;
  first_at: string;
  last_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

type FilterMode = "none" | "onward" | "range";

export default function LogsPage() {
  const { user } = useCurrentUser();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterMode, setFilterMode] = useState<FilterMode>("none");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingLogId, setSavingLogId] = useState<number | null>(null);
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [threadMessages, setThreadMessages] = useState<ChatLog[] | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const pageSize = 20;

  function loadSessions() {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (filterMode === "onward" && startAt) {
      params.set("start_at", new Date(startAt).toISOString());
    }
    if (filterMode === "range") {
      if (startAt) params.set("start_at", new Date(startAt).toISOString());
      if (endAt) params.set("end_at", new Date(endAt).toISOString());
    }
    apiGet<Paginated<SessionSummary>>(`/api/logs/sessions?${params.toString()}`).then((data) => {
      setSessions(data.items);
      setTotal(data.total);
    });
  }

  useEffect(loadSessions, [page, filterMode, startAt, endAt]);

  function handleModeChange(mode: FilterMode) {
    setFilterMode(mode);
    setStartAt("");
    setEndAt("");
    setPage(1);
  }

  async function toggleSession(sessionId: string) {
    if (expandedSessionId === sessionId) {
      setExpandedSessionId(null);
      setThreadMessages(null);
      return;
    }
    setExpandedSessionId(sessionId);
    setThreadMessages(null);
    setThreadLoading(true);
    try {
      const data = await apiGet<ChatLog[]>(`/api/logs/sessions/${encodeURIComponent(sessionId)}`);
      setThreadMessages(data);
    } finally {
      setThreadLoading(false);
    }
  }

  async function handleSaveAsFaq(log: ChatLog) {
    if (!confirm("Save this answer as a new published FAQ entry? The chat log will be removed.")) return;
    setSavingLogId(log.id);
    setError(null);
    try {
      await apiPost(`/api/logs/${log.id}/save-as-faq`, {});
      setThreadMessages((prev) => (prev ? prev.filter((l) => l.id !== log.id) : prev));
      loadSessions();
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
      setExpandedSessionId(null);
      setThreadMessages(null);
      loadSessions();
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
              <th className="px-4 py-2"></th>
              <th className="px-4 py-2">First Question</th>
              <th className="px-4 py-2">IP</th>
              <th className="px-4 py-2">Messages</th>
              <th className="px-4 py-2">Started</th>
              <th className="px-4 py-2">Last Activity</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => {
              const isExpanded = expandedSessionId === session.session_id;
              return (
                <Fragment key={session.session_id}>
                  <tr
                    onClick={() => toggleSession(session.session_id)}
                    className="cursor-pointer border-t border-slate-100 align-top hover:bg-slate-50"
                  >
                    <td className="px-4 py-2 text-slate-400">{isExpanded ? "▾" : "▸"}</td>
                    <td className="max-w-xs px-4 py-2">{session.first_question}</td>
                    <td className="px-4 py-2 text-slate-500">{session.ip_address || "unknown"}</td>
                    <td className="px-4 py-2">{session.message_count}</td>
                    <td className="px-4 py-2 text-slate-500">{new Date(session.first_at).toLocaleString()}</td>
                    <td className="px-4 py-2 text-slate-500">{new Date(session.last_at).toLocaleString()}</td>
                  </tr>
                  {isExpanded && (
                    <tr className="border-t border-slate-100 bg-slate-50">
                      <td colSpan={6} className="px-4 py-3">
                        {threadLoading && <p className="text-xs text-slate-400">Loading conversation...</p>}
                        {!threadLoading && threadMessages && threadMessages.length === 0 && (
                          <p className="text-xs text-slate-400">No messages left in this conversation.</p>
                        )}
                        {!threadLoading && threadMessages && threadMessages.length > 0 && (
                          <div className="flex flex-col gap-3">
                            {threadMessages.map((log) => {
                              const hasMatch = log.matched_faq_ids.length > 0 || log.matched_vault_ids.length > 0;
                              const isSaving = savingLogId === log.id;
                              return (
                                <div key={log.id} className="rounded border border-slate-200 bg-white p-3">
                                  <div className="mb-1 flex items-start justify-between gap-2">
                                    <p className="text-sm font-medium text-slate-800">{log.question_text}</p>
                                    <span className="shrink-0 text-xs text-slate-400">
                                      {new Date(log.created_at).toLocaleString()}
                                    </span>
                                  </div>
                                  <p className="mb-2 text-sm text-slate-600">{log.answer_text}</p>
                                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                                    <span>
                                      Confidence:{" "}
                                      {log.confidence_score !== null ? log.confidence_score.toFixed(2) : "—"}
                                    </span>
                                    <span>
                                      Sources:{" "}
                                      {!hasMatch
                                        ? "—"
                                        : [
                                            log.matched_faq_ids.length > 0
                                              ? `${log.matched_faq_ids.length} FAQ`
                                              : null,
                                            log.matched_vault_ids.length > 0
                                              ? `${log.matched_vault_ids.length} Vault`
                                              : null,
                                          ]
                                            .filter(Boolean)
                                            .join(", ")}
                                    </span>
                                    <span>Engine: {log.engine_used}</span>
                                    {hasMatch && (
                                      <button
                                        onClick={() => handleSaveAsFaq(log)}
                                        disabled={isSaving}
                                        className="ml-auto text-blue-600 disabled:cursor-not-allowed disabled:text-slate-300"
                                      >
                                        {isSaving ? "Saving..." : "Save as FAQ"}
                                      </button>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {sessions.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
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
