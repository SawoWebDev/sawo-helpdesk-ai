"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * A GFM table rendered as its own card, outside the chat bubble.
 *
 * Styling is applied through explicit element renderers wrapped in
 * `not-prose`, rather than `prose-*` overrides: the typography plugin's own
 * table rules are `:where()`-scoped and fight anything set alongside them,
 * and a GFM alignment row ("|:---:|") emits inline styles that beat utility
 * classes. The cell renderers below drop those inline styles entirely, so the
 * alignment here is the alignment that shows.
 *
 * Cells never wrap. Long spec tables scroll sideways within the card instead,
 * which keeps a model code like "SCA-45NS-DRF-P-C" on one line.
 */
export default function ChatTable({ markdown }: { markdown: string }) {
  return (
    <div className="not-prose w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-night-surface">
      <div className="overflow-x-auto">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            table: ({ children }) => (
              <table
                // First column left so model codes scan vertically; every other
                // column centered.
                className="w-full border-collapse text-[12px] [&_td]:text-center [&_th]:text-center [&_tr>*:first-child]:text-left"
              >
                {children}
              </table>
            ),
            thead: ({ children }) => (
              <thead className="bg-slate-50 dark:bg-white/[0.06]">{children}</thead>
            ),
            th: ({ children }) => (
              <th className="whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {children}
              </th>
            ),
            // Zebra striping and hover are scoped to body rows from here so
            // they cannot also catch the header row.
            tbody: ({ children }) => (
              <tbody className="divide-y divide-slate-100 [&>tr:hover]:bg-sawo-light/15 [&>tr:nth-child(even)]:bg-slate-50/60 dark:divide-white/10 dark:[&>tr:hover]:bg-sawo/10 dark:[&>tr:nth-child(even)]:bg-white/[0.03]">
                {children}
              </tbody>
            ),
            td: ({ children }) => (
              <td className="whitespace-nowrap px-3 py-2 align-middle text-slate-700 tabular-nums first:font-medium first:text-slate-900 dark:text-slate-200 dark:first:text-slate-100">
                {children}
              </td>
            ),
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>
    </div>
  );
}