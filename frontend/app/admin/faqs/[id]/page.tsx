"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiGet } from "@/lib/api";
import FAQForm, { FAQFormValues } from "@/components/admin/FAQForm";

export default function EditFAQPage() {
  const params = useParams<{ id: string }>();
  const faqId = Number(params.id);
  const [initial, setInitial] = useState<FAQFormValues | null>(null);

  useEffect(() => {
    apiGet<FAQFormValues>(`/api/faqs/${faqId}`).then(setInitial);
  }, [faqId]);

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800">Edit FAQ Entry</h1>
      {initial ? <FAQForm faqId={faqId} initial={initial} /> : <p className="text-slate-400">Loading...</p>}
    </div>
  );
}
