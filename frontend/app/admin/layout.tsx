"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { logout } from "@/lib/auth";
import { useCurrentUser } from "@/lib/useCurrentUser";
import ThemeToggle from "@/components/chat/ThemeToggle";
import "./admin-cms.css";

/**
 * Nav model, structurally matching the reference SAWO CMS's `NAV_ITEMS`
 * (flat array with { label, href, icon, adminOnly }) — see
 * D:\NEW_SITES\REACT_SITE\SAWO_CMS_DESIGN\05_NAVIGATION\SIDEBAR_NAVIGATION.md.
 * Routes/items themselves are this app's own, not copied from the reference.
 * Icons are Font Awesome 6 class strings (loaded via CDN below), not lucide
 * components — see the icon-library note in layout.tsx's header comment.
 * Rendered as a single flat list, no section grouping/labels.
 */
type NavItem = {
  href: string;
  label: string;
  icon: string;
  adminOnly: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/admin/dashboard", label: "Dashboard", icon: "fa-solid fa-gauge-high", adminOnly: false },
  { href: "/admin/library", label: "Library", icon: "fa-solid fa-book-open", adminOnly: false },
  { href: "/admin/faqs", label: "FAQs", icon: "fa-solid fa-circle-question", adminOnly: false },
  { href: "/admin/knowledge", label: "General Knowledge", icon: "fa-solid fa-brain", adminOnly: false },
  { href: "/admin/logs", label: "Chat Logs", icon: "fa-solid fa-comments", adminOnly: false },
  { href: "/admin/analytics", label: "Analytics", icon: "fa-solid fa-chart-line", adminOnly: false },
  { href: "/admin/settings", label: "Settings", icon: "fa-solid fa-gear", adminOnly: true },
  { href: "/admin/users", label: "Users", icon: "fa-solid fa-users", adminOnly: true },
];

// Segment-boundary aware, ported verbatim from the reference CMS's
// `isNavActive` (AdminLayout.jsx) — a naive `startsWith` would light up
// both a page and an unrelated page whose path happens to prefix it.
function isNavActive(pathname: string | null, href: string) {
  if (!pathname) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

const PENDING_UNANSWERED_POLL_MS = 30000;
const SIDEBAR_COLLAPSED_KEY = "admin_sidebar_collapsed";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading } = useCurrentUser();
  const isLoginPage = pathname === "/admin/login";
  const [hasPendingUnanswered, setHasPendingUnanswered] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

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

  // Sidebar collapsed/expanded state persists across sessions, same key
  // convention as the reference CMS's `localStorage["admin_sidebar_collapsed"]`.
  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1");
    } catch {
      // storage unavailable — default to expanded
    }
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        // ignore
      }
      return next;
    });
  }

  // Mobile drawer closes automatically on route change, and locks body
  // scroll while open — matching the reference CMS's mobile menu behavior.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

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

  const visibleItems = NAV_ITEMS.filter((item) => !item.adminOnly || user.role === "admin");

  function handleLogout() {
    logout();
    router.replace("/admin/login");
  }

  const navSections = (onNavigate?: () => void) => (
    <nav className="cms-sidebar-nav">
      {visibleItems.map((item) => {
        const active = isNavActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={`cms-sidebar-nav-item${active ? " is-active" : ""}`}
          >
            <span className="cms-sidebar-nav-icon">
              <i className={item.icon} aria-hidden="true" />
            </span>
            <span className="cms-sidebar-nav-label">{item.label}</span>
            {item.href === "/admin/faqs" && hasPendingUnanswered && (
              <span aria-label="New unanswered questions" className="cms-sidebar-nav-dot" />
            )}
          </Link>
        );
      })}
    </nav>
  );

  const footerCard = (
    <div className="cms-sidebar-footer">
      <div className="cms-sidebar-footer-text">
        <p className="cms-sidebar-footer-name">{user.username}</p>
        <p className="cms-sidebar-footer-role">{user.role}</p>
      </div>
      <div className="cms-sidebar-footer-actions">
        <button type="button" onClick={handleLogout} className="cms-sidebar-footer-btn" title="Log out" aria-label="Log out">
          <i className="fa-solid fa-right-from-bracket" aria-hidden="true" />
        </button>
        <ThemeToggle />
      </div>
    </div>
  );

  return (
    <div className="cms-admin-shell">
      {/* Font Awesome 6.5.1, loaded via CDN exactly as the reference CMS
          does (async, non-blocking media=print swap trick) — scoped to the
          admin chrome only, not the public chat widget. See
          06_ICONS/ICON_SYSTEM.md in the design reference. */}
      <link
        rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"
        media="print"
        onLoad={(e) => {
          (e.currentTarget as HTMLLinkElement).media = "all";
        }}
      />

      {/* Mobile-only topbar (≤768px) — hamburger + logo + theme toggle.
          The page title itself is intentionally left to the (always-visible)
          per-page header below rather than duplicated here. */}
      <header className="cms-topbar">
        <button
          type="button"
          className="cms-topbar-burger"
          aria-label="Open navigation"
          onClick={() => setMobileOpen(true)}
        >
          <i className="fa-solid fa-bars" aria-hidden="true" />
        </button>
        <Image src="/sawo-logo.png" alt="Sawo" width={26} height={26} className="cms-topbar-logo" />
        <span className="cms-topbar-spacer" />
        <ThemeToggle />
      </header>

      <div
        className={`cms-sidebar-overlay${mobileOpen ? " is-visible" : ""}`}
        onClick={() => setMobileOpen(false)}
      />

      <aside className={`cms-sidebar${collapsed ? " is-collapsed" : ""}${mobileOpen ? " is-mobile-open" : ""}`}>
        <button
          type="button"
          className="cms-sidebar-collapse-btn"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <i className={`fa-solid fa-chevron-${collapsed ? "right" : "left"}`} aria-hidden="true" />
        </button>

        <Link href="/" target="_blank" rel="noopener noreferrer" className="cms-sidebar-logo">
          <Image src="/sawo-logo.png" alt="Sawo" width={32} height={32} className="cms-sidebar-logo-img" />
          <div className="cms-sidebar-logo-text">
            <strong>Helpdesk Admin</strong>
            <span>SAWO</span>
          </div>
        </Link>

        {navSections(() => setMobileOpen(false))}

        {footerCard}
      </aside>

      <main className="cms-admin-main">
        <div className="cms-admin-main-content">{children}</div>
      </main>
    </div>
  );
}
