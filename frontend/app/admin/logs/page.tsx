"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import Pagination from "@/components/admin/Pagination";

interface ChatLog {
  id: number;
  question_text: string;
  answer_text: string;
  matched_faq_ids: number[];
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
  const [logs, setLogs] = useState<ChatLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterMode, setFilterMode] = useState<FilterMode>("none");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const pageSize = 20;

  useEffect(() => {
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
  }, [page, filterMode, startAt, endAt]);

  function handleModeChange(mode: FilterMode) {
    setFilterMode(mode);
    setStartAt("");
    setEndAt("");
    setPage(1);
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800">Chat Logs</h1>

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
              <th className="px-4 py-2">Engine</th>
              <th className="px-4 py-2">Time</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="border-t border-slate-100 align-top">
                <td className="max-w-xs px-4 py-2">{log.question_text}</td>
                <td className="max-w-xs truncate px-4 py-2">{log.answer_text}</td>
                <td className="px-4 py-2">
                  {log.confidence_score !== null ? log.confidence_score.toFixed(2) : "—"}
                </td>
                <td className="px-4 py-2">{log.engine_used}</td>
                <td className="px-4 py-2 text-slate-500">{new Date(log.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
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
