"use client";

import FAQForm from "@/components/admin/FAQForm";
import PageHeader from "@/components/admin/PageHeader";

export default function NewFAQPage() {
  return (
    <div>
      <PageHeader icon="fa-solid fa-circle-question" title="New FAQ Entry" />
      <FAQForm />
    </div>
  );
}
