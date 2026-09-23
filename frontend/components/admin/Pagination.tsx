"use client";

export default function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600 dark:border-white/10 dark:text-slate-400">
      <span>
        Page {page} of {totalPages} ({total} total)
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent dark:border-white/15 dark:text-slate-200 dark:hover:bg-white/5 dark:disabled:text-slate-500 dark:disabled:hover:bg-transparent"
        >
          Previous
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent dark:border-white/15 dark:text-slate-200 dark:hover:bg-white/5 dark:disabled:text-slate-500 dark:disabled:hover:bg-transparent"
        >
          Next
        </button>
      </div>
    </div>
  );
}
