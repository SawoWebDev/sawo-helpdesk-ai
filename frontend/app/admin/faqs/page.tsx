"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import FaqsListTab from "@/components/admin/faqs/FaqsListTab";
import UnansweredTab from "@/components/admin/faqs/UnansweredTab";
import CategoriesTab from "@/components/admin/faqs/CategoriesTab";
import PageHeader from "@/components/admin/PageHeader";

type TabKey = "faqs" | "unanswered" | "categories";

const TABS: { key: TabKey; label: string }[] = [
  { key: "faqs", label: "FAQs" },
  { key: "unanswered", label: "Unanswered" },
  { key: "categories", label: "Categories" },
];

export default function FaqsPage() {
  const [tab, setTab] = useState<TabKey>("faqs");
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("tab");
    if (requested === "unanswered" || requested === "categories") setTab(requested);
  }, []);

  async function refreshPendingCount() {
    const data = await apiGet<{ total: number }>("/api/unanswered?page=1&page_size=1&status=pending");
    setPendingCount(data.total);
  }

  useEffect(() => {
    refreshPendingCount();
  }, []);

  return (
    <div>
      <PageHeader
        icon="fa-solid fa-circle-question"
        title="FAQ Knowledge Base"
        description="Manage FAQ entries and review unanswered chat questions."
      />

      <div className="mb-6 flex items-center gap-1 border-b border-slate-200 dark:border-white/10">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`relative flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? "border-sawo text-sawo-dark dark:border-sawo-light dark:text-sawo-light"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {t.label}
            {t.key === "unanswered" && pendingCount > 0 && (
              <span aria-label="New unanswered questions" className="h-2 w-2 rounded-full bg-red-500" />
            )}
          </button>
        ))}
      </div>

      {tab === "faqs" && <FaqsListTab />}
      {tab === "unanswered" && <UnansweredTab onChange={refreshPendingCount} />}
      {tab === "categories" && <CategoriesTab />}
    </div>
  );
}
