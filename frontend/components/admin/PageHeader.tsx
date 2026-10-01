import { ReactNode } from "react";
import ReportsBell from "@/components/admin/ReportsBell";

/**
 * Shared per-page header for the admin CMS chrome, structurally matching the
 * reference SAWO CMS's `PageHeader.jsx` (icon chip + title + description,
 * actions slot on the right) — see
 * D:\NEW_SITES\REACT_SITE\SAWO_CMS_DESIGN\02_LAYOUT\HEADER.md.
 *
 * Unlike the reference (where `AdminLayout` renders this automatically from
 * a route table), each admin page renders its own `<PageHeader>` directly,
 * since our pages' titles/descriptions/actions are page-local state (search
 * queries, date-range tabs, toggle switches) rather than derivable from a
 * static nav-item lookup. This keeps the component itself fully reusable
 * (one implementation, styled once in admin-cms.css) without copy-pasting
 * markup into every page.
 */
export default function PageHeader({
  icon,
  title,
  description,
  actions,
}: {
  /** Font Awesome 6 class string, e.g. "fa-solid fa-gauge-high". */
  icon: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="cms-page-header">
      <div className="cms-page-header-main">
        <div className="cms-page-header-icon">
          <i className={icon} aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <h1 className="cms-page-title">{title}</h1>
          {description && <p className="cms-page-description">{description}</p>}
        </div>
      </div>
      {/* Always rendered (not just when a page passes `actions`) so the
          reports bell shows up consistently in every page's header, inside
          its flex row — not floated/fixed on top of it, which is what was
          clipping/overlapping it before. */}
      <div className="cms-page-header-actions">
        {actions}
        <ReportsBell />
      </div>
    </div>
  );
}
