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

export default function LogsPage() {
  const [logs, setLogs] = useState<ChatLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  useEffect(() => {
    apiGet<Paginated<ChatLog>>(`/api/logs?page=${page}&page_size=${pageSize}`).then((data) => {
      setLogs(data.items);
      setTotal(data.total);
    });
  }, [page]);

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800">Chat Logs</h1>
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
          </tbody>
        </table>
        <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
      </div>
    </div>
  );
}
