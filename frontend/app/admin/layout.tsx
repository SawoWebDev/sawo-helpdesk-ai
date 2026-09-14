"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { logout } from "@/lib/auth";
import { useCurrentUser } from "@/lib/useCurrentUser";

const NAV_ITEMS = [
  { href: "/admin/dashboard", label: "Dashboard", adminOnly: false },
  { href: "/admin/library", label: "Library", adminOnly: false },
  { href: "/admin/faqs", label: "FAQs", adminOnly: false },
  { href: "/admin/categories", label: "Categories", adminOnly: false },
  { href: "/admin/unanswered", label: "Unanswered", adminOnly: false },
  { href: "/admin/logs", label: "Chat Logs", adminOnly: false },
  { href: "/admin/settings", label: "Settings", adminOnly: true },
  { href: "/admin/users", label: "Users", adminOnly: true },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading } = useCurrentUser();
  const isLoginPage = pathname === "/admin/login";

  useEffect(() => {
    if (!loading && !user && !isLoginPage) {
      router.replace("/admin/login");
    }
  }, [loading, user, isLoginPage, router]);

  if (isLoginPage) return <>{children}</>;

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-slate-500">Loading...</div>;
  }

  if (!user) {
    return null;
  }

  return (
    <div className="flex h-screen bg-slate-50">
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-4">
          <p className="font-semibold text-slate-800">Helpdesk Admin</p>
          <p className="text-xs text-slate-500">
            {user.username} · {user.role}
          </p>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-2">
          {NAV_ITEMS.filter((item) => !item.adminOnly || user.role === "admin").map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded px-3 py-2 text-sm ${
                pathname?.startsWith(item.href)
                  ? "bg-blue-50 font-medium text-blue-700"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-2">
          <button
            onClick={() => {
              logout();
              router.replace("/admin/login");
            }}
            className="w-full rounded px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-100"
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
