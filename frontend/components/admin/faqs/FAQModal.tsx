"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { apiGet } from "@/lib/api";
import FAQForm, { FAQFormValues } from "@/components/admin/FAQForm";

export default function FAQModal({
  faqId,
  onClose,
  onSaved,
}: {
  faqId?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [initial, setInitial] = useState<FAQFormValues | null>(null);
  const isEdit = faqId != null;

  useEffect(() => {
    if (faqId == null) {
      setInitial({ question: "", answer: "", category_id: null, image_urls: [], reference_urls: [] });
      return;
    }
    setInitial(null);
    apiGet<FAQFormValues>(`/api/faqs/${faqId}`).then(setInitial);
  }, [faqId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl dark:bg-night-surface"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-white/10">
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
            {isEdit ? "Edit FAQ Entry" : "New FAQ Entry"}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:text-slate-500 dark:hover:bg-white/10"
          >
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto p-5">
          {initial ? (
            <FAQForm faqId={faqId} initial={initial} onSaved={onSaved} onCancel={onClose} />
          ) : (
            <p className="text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </div>
      </div>
    </div>
  );
}
