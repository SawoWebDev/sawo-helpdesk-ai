"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api";

interface Paginated {
  total: number;
}

export default function DashboardPage() {
  const [faqCount, setFaqCount] = useState<number | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);

  useEffect(() => {
    apiGet<Paginated>("/api/faqs?page=1&page_size=1").then((r) => setFaqCount(r.total));
    apiGet<Paginated>("/api/unanswered?page=1&page_size=1&status=pending").then((r) =>
      setPendingCount(r.total)
    );
  }, []);

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800 dark:text-slate-100">Dashboard</h1>
      <div className="grid grid-cols-2 gap-4">
        <Link
          href="/admin/faqs"
          className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm hover:border-sawo/40 dark:border-white/10 dark:bg-night-surface dark:hover:border-sawo-light/50"
        >
          <p className="text-sm text-slate-500 dark:text-slate-400">Knowledge Base Entries</p>
          <p className="mt-1 text-3xl font-semibold text-slate-800 dark:text-slate-100">{faqCount ?? "..."}</p>
        </Link>
        <Link
          href="/admin/unanswered"
          className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm hover:border-sawo/40 dark:border-white/10 dark:bg-night-surface dark:hover:border-sawo-light/50"
        >
          <p className="text-sm text-slate-500 dark:text-slate-400">Pending Unanswered Questions</p>
          <p className="mt-1 text-3xl font-semibold text-slate-800 dark:text-slate-100">{pendingCount ?? "..."}</p>
        </Link>
      </div>
    </div>
  );
}
