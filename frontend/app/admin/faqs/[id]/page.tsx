"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiGet } from "@/lib/api";
import FAQForm, { FAQFormValues } from "@/components/admin/FAQForm";
import PageHeader from "@/components/admin/PageHeader";

export default function EditFAQPage() {
  const params = useParams<{ id: string }>();
  const faqId = Number(params.id);
  const [initial, setInitial] = useState<FAQFormValues | null>(null);

  useEffect(() => {
    apiGet<FAQFormValues>(`/api/faqs/${faqId}`).then(setInitial);
  }, [faqId]);

  return (
    <div>
      <PageHeader icon="fa-solid fa-circle-question" title="Edit FAQ Entry" />
      {initial ? <FAQForm faqId={faqId} initial={initial} /> : <p className="text-slate-400 dark:text-slate-500">Loading...</p>}
    </div>
  );
}
