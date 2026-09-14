"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useCurrentUser } from "@/lib/useCurrentUser";

export default function AdminIndexPage() {
  const router = useRouter();
  const { user, loading } = useCurrentUser();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/admin/dashboard" : "/admin/login");
  }, [loading, user, router]);

  return null;
}
