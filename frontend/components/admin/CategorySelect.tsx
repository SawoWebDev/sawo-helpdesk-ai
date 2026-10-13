"use client";

export interface CategoryOption {
  id: number;
  name: string;
  parent_id: number | null;
}

function buildLabel(categories: CategoryOption[], category: CategoryOption): string {
  const path: string[] = [category.name];
  let current = category;
  while (current.parent_id !== null) {
    const parent = categories.find((c) => c.id === current.parent_id);
    if (!parent) break;
    path.unshift(parent.name);
    current = parent;
  }
  return path.join(" > ");
}

export default function CategorySelect({
  categories,
  value,
  onChange,
  allowEmpty = true,
}: {
  categories: CategoryOption[];
  value: number | null;
  onChange: (id: number | null) => void;
  allowEmpty?: boolean;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
    >
      {allowEmpty && <option value="" className="dark:bg-night-surface dark:text-slate-100">No category</option>}
      {categories.map((c) => (
        <option key={c.id} value={c.id} className="dark:bg-night-surface dark:text-slate-100">
          {buildLabel(categories, c)}
        </option>
      ))}
    </select>
  );
}
