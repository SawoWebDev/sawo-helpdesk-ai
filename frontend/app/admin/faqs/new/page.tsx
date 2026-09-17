"use client";

import FAQForm from "@/components/admin/FAQForm";

export default function NewFAQPage() {
  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800 dark:text-slate-100">New FAQ Entry</h1>
      <FAQForm />
    </div>
  );
}
