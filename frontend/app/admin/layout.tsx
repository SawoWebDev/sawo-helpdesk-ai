"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { logout } from "@/lib/auth";
import { useCurrentUser } from "@/lib/useCurrentUser";
import ThemeToggle from "@/components/chat/ThemeToggle";
import {
  AnalyticsIcon,
  DashboardIcon,
  FaqIcon,
  LibraryIcon,
  LogoutIcon,
  LogsIcon,
  SettingsIcon,
  UsersIcon,
} from "@/components/admin/AdminIcons";

const NAV_ITEMS = [
  { href: "/admin/dashboard", label: "Dashboard", adminOnly: false, icon: DashboardIcon },
  { href: "/admin/logs", label: "Chat Logs", adminOnly: false, icon: LogsIcon },
  { href: "/admin/library", label: "Library", adminOnly: false, icon: LibraryIcon },
  { href: "/admin/faqs", label: "FAQs", adminOnly: false, icon: FaqIcon },
  { href: "/admin/analytics", label: "Analytics", adminOnly: false, icon: AnalyticsIcon },
  { href: "/admin/settings", label: "Settings", adminOnly: true, icon: SettingsIcon },
  { href: "/admin/users", label: "Users", adminOnly: true, icon: UsersIcon },
];

const PENDING_UNANSWERED_POLL_MS = 30000;

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading } = useCurrentUser();
  const isLoginPage = pathname === "/admin/login";
  const [hasPendingUnanswered, setHasPendingUnanswered] = useState(false);

  useEffect(() => {
    if (!loading && !user && !isLoginPage) {
      router.replace("/admin/login");
    }
  }, [loading, user, isLoginPage, router]);

  useEffect(() => {
    if (!user || isLoginPage) return;
    let cancelled = false;
    function checkPending() {
      apiGet<{ total: number }>("/api/unanswered?page=1&page_size=1&status=pending")
        .then((data) => {
          if (!cancelled) setHasPendingUnanswered(data.total > 0);
        })
        .catch(() => {});
    }
    checkPending();
    const interval = setInterval(checkPending, PENDING_UNANSWERED_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [user, isLoginPage, pathname]);

  if (isLoginPage) return <>{children}</>;

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 text-slate-500 dark:bg-night-bg dark:text-slate-400">
        Loading...
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-night-bg dark:text-slate-100">
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
        <Link
          href="/"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2.5 border-b border-slate-200 px-4 py-4 transition-colors hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
        >
          <Image src="/sawo-logo.png" alt="Sawo" width={28} height={28} className="shrink-0 rounded" />
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-800 dark:text-slate-100">Helpdesk Admin</p>
            <p className="truncate text-xs text-slate-500 dark:text-slate-400">
              {user.username} · {user.role}
            </p>
          </div>
        </Link>
        <nav className="flex flex-1 flex-col gap-1 p-2">
          {NAV_ITEMS.filter((item) => !item.adminOnly || user.role === "admin").map((item) => {
            const Icon = item.icon;
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative flex items-center gap-2.5 rounded px-3 py-2 text-sm font-semibold transition-colors ${
                  active
                    ? "bg-sawo text-white dark:bg-sawo-dark"
                    : "text-slate-600 hover:bg-sawo hover:text-white dark:text-slate-300 dark:hover:bg-sawo-dark dark:hover:text-white"
                }`}
              >
                <Icon />
                {item.label}
                {item.href === "/admin/faqs" && hasPendingUnanswered && (
                  <span
                    aria-label="New unanswered questions"
                    className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full bg-red-500"
                  />
                )}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center justify-between border-t border-slate-200 p-2 dark:border-white/10">
          <button
            onClick={() => {
              logout();
              router.replace("/admin/login");
            }}
            className="flex flex-1 items-center gap-2.5 rounded px-3 py-2 text-left text-sm font-semibold text-slate-600 transition-colors hover:bg-sawo hover:text-white dark:text-slate-300 dark:hover:bg-sawo-dark dark:hover:text-white"
          >
            <LogoutIcon />
            Log out
          </button>
          <ThemeToggle variant="neutral" />
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
